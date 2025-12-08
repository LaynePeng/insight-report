#!/usr/bin/env python3
"""
YouTube技术洞察报告生成器
从YouTube视频提取字幕并使用LLM生成技术分析报告。
支持长字幕自动分块处理。
"""

import re
import yaml
import time
import requests
import yt_dlp
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class ConfigLoader:
    """配置加载器，负责加载和验证配置文件"""
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path

    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            print(f"❌ 错误: 配置文件 {self.config_path} 不存在ảng")
            print("请确保目录下存在正确的 config.yaml 文件ảng")
            sys.exit(1)
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file) or {}
                return config
        except yaml.YAMLError as e:
            print(f"❌ 配置文件格式错误: {e}")
            sys.exit(1)

class CacheManager:
    """缓存管理器，负责文件读写和临时目录管理"""
    def __init__(self, reports_dir: str):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def get_temp_dir(self, video_id: str) -> Path:
        """获取特定视频的临时目录"""
        temp_dir = self.reports_dir / "temp" / video_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def save_text(self, path: Path, content: str):
        """保存文本到文件"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def load_text(self, path: Path) -> str:
        """从文件加载文本"""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def exists(self, path: Path) -> bool:
        """检查文件是否存在"""
        return path.exists()

class SubtitleService:
    """字幕服务，负责提取和清洗字幕"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('subtitle', {})

    def extract_subtitle(self, video_url: str, temp_dir: Path) -> str:
        """使用 yt-dlp 提取字幕"""
        temp_prefix = f"temp_sub_{int(time.time())}"
        preferred_languages = self.config.get('preferred_languages', ['en'])
        browser_for_cookies = self.config.get('browser_for_cookies')
        cookies_file = self.config.get('cookies_file')
        
        # 构建完整的输出模板路径，将字幕文件保存到 temp_dir 中
        output_template = str(temp_dir / temp_prefix)

        ydl_opts: Dict[str, Any] = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': preferred_languages,
            'subtitlesformat': 'vtt',
            'outtmpl': output_template, # 使用完整的路径
            'quiet': True,
            'no_warnings': True,
            'no_check_certificate': True,
        }

        # --- Cookie 配置 ---
        if browser_for_cookies:
            print(f"尝试从浏览器 '{browser_for_cookies}' 自动加载 cookies...")
            ydl_opts['cookiesfrombrowser'] = (browser_for_cookies, )
        elif cookies_file and os.path.exists(cookies_file):
            print(f"使用 cookies 文件: {cookies_file}")
            ydl_opts['cookies'] = cookies_file

        downloaded_file = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
                print("正在获取视频信息并下载字幕...")
                ydl.extract_info(video_url, download=True)
                
                # 查找下载的文件
                downloaded_file_path = None
                for file in os.listdir(temp_dir):
                    if file.startswith(temp_prefix) and file.endswith('.vtt'):
                        downloaded_file_path = temp_dir / file
                        break
                
                if not downloaded_file_path:
                    raise ValueError("未找到可下载的字幕文件ảng")

                with open(downloaded_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                return self._clean_vtt_text(content)
        except Exception as e:
            raise RuntimeError(f"字幕提取失败: {e}")
        finally:
            if downloaded_file_path and os.path.exists(downloaded_file_path): # type: ignore
                os.remove(downloaded_file_path)

    def _clean_vtt_text(self, vtt_text: str) -> str:
        """清洗 VTT 字幕格式"""
        lines = vtt_text.splitlines()
        cleaned_lines = []
        seen_lines = set()
        for line in lines:
            line = line.strip()
            if '-->' in line or line.isdigit() or not line or \
               line.startswith('WEBVTT') or line.startswith('Kind:') or \
               line.startswith('Language:'):
                continue
            line = re.sub(r'<[^>]+>', '', line)
            if line not in seen_lines:
                cleaned_lines.append(line)
                seen_lines.add(line)
        return "\n".join(cleaned_lines)

class LLMService:
    """LLM 服务，负责与大模型 API 交互"""
    def __init__(self, config: Dict[str, Any], api_key: str):
        self.config = config.get('llm', {})
        self.api_key = api_key
        self.provider = self.config.get('provider', 'openai')
        self.base_url = self.config.get('base_url', '').rstrip('/')
        self.model = self.config.get('model')
        
        if self.provider == 'gemini':
            try:
                import google.generativeai as genai
                self.genai = genai
                self.genai.configure(api_key=self.api_key) # type: ignore
                self.genai_model = self.genai.GenerativeModel(self.model) # type: ignore
            except ImportError:
                print("❌ 错误: 未找到 google-generativeai 库。请运行 pip install google-generativeai")
                sys.exit(1)

    def call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM API"""
        if self.provider == 'gemini':
            return self._call_gemini(system_prompt, user_prompt)
        else:
            return self._call_openai(system_prompt, user_prompt)

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        try:
            # Gemini SDK 建议将 system prompt 包含在 model配置中或直接拼接
            # 这里采用拼接方式以支持动态 system prompt
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = self.genai_model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            raise RuntimeError(f"Gemini API 调用失败: {e}")

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.5,
        }

        try:
            url = f"{self.base_url}/chat/completions"
            response = requests.post(url, headers=headers, json=data, timeout=180)
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except requests.RequestException as e:
            error_msg = f"API 请求失败: {e}"
            if e.response is not None:
                error_msg += f", 响应: {e.response.text}"
            raise RuntimeError(error_msg)

class YouTubeAnalyzer:
    """主分析器，协调各个服务生成报告"""
    def __init__(self, 
                 config: Dict[str, Any], 
                 subtitle_service: SubtitleService, 
                 llm_service: LLMService, 
                 cache_manager: CacheManager):
        self.config = config
        self.subtitle_service = subtitle_service
        self.llm_service = llm_service
        self.cache_manager = cache_manager
        self.prompts_config = config.get('prompts', {})

    def _get_video_id(self, video_url: str) -> str:
        """从 URL 提取视频 ID"""
        match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', video_url)
        if not match:
            raise ValueError("无法从 URL 中提取有效的 YouTube 视频 ID")
        return match.group(1)

    def _generate_report_for_chunk(self, transcript_chunk: str, is_summary: bool) -> str:
        """为单个文本块生成报告或摘要"""
        system_prompt = self.prompts_config.get('system_prompt', '')
        
        if is_summary:
            prompt_template = self.prompts_config.get('summary_prompt', '{transcript}')
        else:
            prompt_template = self.prompts_config.get('analysis_prompt', '{transcript}')
            
        user_prompt = prompt_template.format(transcript=transcript_chunk)
        return self.llm_service.call_llm(system_prompt, user_prompt)

    def _process_long_transcript(self, transcript: str, temp_dir: Path) -> str:
        """处理长字幕：分块 -> 总结 -> 整合分析"""
        max_chars = self.config.get('llm', {}).get('max_chars', 15000)
        
        if len(transcript) <= max_chars:
            print("字幕长度适中，直接生成报告...")
            return self._generate_report_for_chunk(transcript, is_summary=False)

        print(f"字幕过长({len(transcript)} > {max_chars})，启动分块总结模式ảng")
        chunks = [transcript[i:i+max_chars] for i in range(0, len(transcript), max_chars)]
        summaries = []

        for i, chunk in enumerate(chunks):
            summary_path = temp_dir / f"chunk_{i+1}_summary.txt"
            
            if self.cache_manager.exists(summary_path):
                print(f"分块 {i+1}/{len(chunks)} 的摘要已存在，从缓存加载...")
                summary = self.cache_manager.load_text(summary_path)
            else:
                print(f"正在处理分块 {i+1}/{len(chunks)}...")
                summary = self._generate_report_for_chunk(chunk, is_summary=True)
                self.cache_manager.save_text(summary_path, summary)
                print(f"分块 {i+1} 总结完成，并已缓存ảng")
            
            summaries.append(summary)

        print("所有分块总结完毕，正在进行最终整合分析...")
        combined_summary = "\n\n".join(summaries)
        
        # 保存整合后的摘要以便调试
        combined_summary_path = temp_dir / "combined_summary.txt"
        self.cache_manager.save_text(combined_summary_path, combined_summary)
        
        final_report = self._generate_report_for_chunk(combined_summary, is_summary=False)
        return final_report

    def run(self, video_url: str):
        """执行主流程"""
        try:
            video_id = self._get_video_id(video_url)
            temp_dir = self.cache_manager.get_temp_dir(video_id)
            
            print(f"=== 开始分析视频: {video_url} (ID: {video_id}) ===")
            
            # 1. 获取字幕
            transcript_path = temp_dir / "transcript.txt"
            if self.cache_manager.exists(transcript_path):
                print("从缓存加载字幕...")
                transcript = self.cache_manager.load_text(transcript_path)
            else:
                transcript = self.subtitle_service.extract_subtitle(video_url, temp_dir)
                self.cache_manager.save_text(transcript_path, transcript)
            
            print(f"字幕处理完成，长度: {len(transcript)} 字符ảng")

            # 2. 生成报告
            report = self._process_long_transcript(transcript, temp_dir)
            
            # 3. 保存最终报告
            report_format = self.config.get('output', {}).get('format', 'md')
            report_filename = f"{video_id}_report.{report_format}"
            report_path = self.cache_manager.reports_dir / report_filename
            self.cache_manager.save_text(report_path, report)
            
            print("\n" + "="*30)
            print("✅ 报告生成成功ảng")
            print(f"📄 文件路径: {report_path}")
            print(f"ℹ️  中间文件保存在: {temp_dir}")
            print("="*30 + "\n")
            print("--- 报告预览 ---")
            print(report[:400] + "..." if len(report) > 400 else report)

        except (RuntimeError, ValueError) as e:
            print(f"\n❌ 任务失败: {e}")

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='YouTube AI 报告生成器',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('url', help='YouTube 视频链接')
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    parser.add_argument(
        '--api-key', 
        help='LLM API Key。\n优先级: 此参数 > 环境变量(LLM_API_KEY) > 配置文件 > 手动输入'
    )
    args = parser.parse_args()

    # 1. 加载配置
    config_loader = ConfigLoader(args.config)
    config = config_loader.load_config()

    # 2. 获取 API Key
    api_key = args.api_key or os.getenv("LLM_API_KEY") or config.get('llm', {}).get('api_key')
    if not api_key or "YOUR_API_KEY" in api_key:
        api_key = input("请输入你的LLM API Key: ").strip()
        if not api_key:
            print("❌ 错误: 未提供有效的API Keyảng")
            sys.exit(1)

    # 3. 初始化服务
    cache_manager = CacheManager(config.get('output', {}).get('reports_dir', 'reports'))
    subtitle_service = SubtitleService(config)
    llm_service = LLMService(config, api_key)

    # 4. 运行分析器
    analyzer = YouTubeAnalyzer(config, subtitle_service, llm_service, cache_manager)
    analyzer.run(args.url)

if __name__ == "__main__":
    main()