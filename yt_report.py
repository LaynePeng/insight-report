#!/usr/bin/env python3
"""
YouTube技术洞察报告生成器 (重构版)
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

class YouTubeAnalyzer:
    """
    主分析器类，整合了配置加载、字幕提取、LLM分析和文件保存功能。
    """

    DEFAULT_CONFIG = """
llm:
  base_url: "https://api.openai.com/v1"
  api_key: ""
  model: "gpt-3.5-turbo"
  max_chars: 15000  # 字幕分块处理的单块最大字符数

prompts:
  system_prompt: "你是一名专业的技术分析师，擅长从技术视频内容中提取关键洞察。"
  analysis_prompt: |
    请分析以下视频字幕内容，生成一份技术洞察报告。
    报告应包含核心技术概念、关键要点总结、实践应用建议等。
    请使用清晰、专业的中文输出。

    字幕内容：
    {transcript}
  
  summary_prompt: |
    请总结以下字幕的核心内容，用于后续的整合分析。
    总结应简明扼要，突出关键信息。

    字幕内容：
    {transcript}

subtitle:
  preferred_languages: ['zh-Hans', 'zh-CN', 'zh', 'en']

output:
  reports_dir: "reports"
  save_subtitles: true
  format: "md"
"""

    def __init__(self, config_path: str = "config.yaml", api_key: Optional[str] = None):
        self.config_path = config_path
        self.config = self._load_or_create_config()
        
        # API Key 优先级: 命令行参数 > 环境变量 > 配置文件
        self.api_key = api_key or os.getenv("LLM_API_KEY") or self.config.get('llm', {}).get('api_key')
        
        if not self.api_key or "YOUR_API_KEY" in self.api_key:
            self.api_key = input("请输入你的LLM API Key: ").strip()
            if not self.api_key:
                print("错误: 未提供有效的API Key。")
                sys.exit(1)

        self.reports_dir = Path(self.config.get('output', {}).get('reports_dir', 'reports'))
        self.reports_dir.mkdir(exist_ok=True)

    def _load_or_create_config(self) -> Dict[str, Any]:
        """加载或创建配置文件"""
        if not os.path.exists(self.config_path):
            print(f"配置文件 {self.config_path} 不存在，创建默认模板...")
            try:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    f.write(self.DEFAULT_CONFIG)
                print(f"默认配置已创建，你可以在 {self.config_path} 中修改。")
            except IOError as e:
                print(f"无法创建配置文件: {e}")
                sys.exit(1)
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file) or {}
        except yaml.YAMLError as e:
            print(f"配置文件格式错误: {e}")
            sys.exit(1)

    def _extract_subtitle(self, video_url: str) -> str:
        """使用 yt-dlp 提取字幕"""
        temp_prefix = f"temp_sub_{int(time.time())}"
        subtitle_config = self.config.get('subtitle', {})
        preferred_languages = subtitle_config.get('preferred_languages', ['en'])
        browser_for_cookies = subtitle_config.get('browser_for_cookies')
        cookies_file = subtitle_config.get('cookies_file')
        
        ydl_opts: Dict[str, Any] = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': preferred_languages,
            'subtitlesformat': 'vtt',
            'outtmpl': temp_prefix,
            'quiet': True,
            'no_warnings': True,
            'no_check_certificate': True, # 解决 SSL 证书问题
        }

        # --- Cookie 配置 ---
        # 优先使用 browser_for_cookies
        if browser_for_cookies:
            print(f"尝试从浏览器 '{browser_for_cookies}' 自动加载 cookies...")
            ydl_opts['cookiesfrombrowser'] = (browser_for_cookies, )
        elif cookies_file and os.path.exists(cookies_file):
            print(f"使用 cookies 文件: {cookies_file}")
            ydl_opts['cookies'] = cookies_file

        downloaded_file = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print("正在获取视频信息并下载字幕...")
                ydl.extract_info(video_url, download=True)
                
                for file in os.listdir('.'):
                    if file.startswith(temp_prefix) and file.endswith('.vtt'):
                        downloaded_file = file
                        break
                
                if not downloaded_file:
                    raise ValueError("未找到可下载的字幕文件。")

                with open(downloaded_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                return self._clean_vtt_text(content)
        except Exception as e:
            raise RuntimeError(f"字幕提取失败: {e}")
        finally:
            if downloaded_file and os.path.exists(downloaded_file):
                os.remove(downloaded_file)

    def _clean_vtt_text(self, vtt_text: str) -> str:
        """清理 VTT 字幕格式"""
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

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用LLM API"""
        llm_config = self.config.get('llm', {})
        base_url = llm_config.get('base_url', '').rstrip('/')
        model = llm_config.get('model')

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.5,
        }

        try:
            url = f"{base_url}/chat/completions"
            response = requests.post(url, headers=headers, json=data, timeout=180)
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except requests.RequestException as e:
            raise RuntimeError(f"API 请求失败: {e}, 响应: {e.response.text if e.response else 'N/A'}")

    def _generate_report_for_chunk(self, transcript_chunk: str, is_summary: bool) -> str:
        """为单个文本块生成报告或摘要"""
        prompts_config = self.config.get('prompts', {})
        system_prompt = prompts_config.get('system_prompt', '')
        
        if is_summary:
            prompt_template = prompts_config.get('summary_prompt', '{transcript}')
        else:
            prompt_template = prompts_config.get('analysis_prompt', '{transcript}')
            
        user_prompt = prompt_template.format(transcript=transcript_chunk)
        return self._call_llm(system_prompt, user_prompt)

    def _process_long_transcript(self, transcript: str) -> str:
        """处理长字幕，分块总结再整合分析"""
        max_chars = self.config.get('llm', {}).get('max_chars', 15000)
        
        if len(transcript) <= max_chars:
            print("字幕长度适中，直接生成报告...")
            return self._generate_report_for_chunk(transcript, is_summary=False)

        print(f"字幕过长({len(transcript)} > {max_chars})，启动分块总结模式...")
        chunks = [transcript[i:i+max_chars] for i in range(0, len(transcript), max_chars)]
        summaries = []

        for i, chunk in enumerate(chunks):
            print(f"正在处理分块 {i+1}/{len(chunks)}...")
            summary = self._generate_report_for_chunk(chunk, is_summary=True)
            summaries.append(summary)
            print(f"分块 {i+1} 总结完成。")

        print("所有分块总结完毕，正在进行最终整合分析...")
        combined_summary = "\n\n".join(summaries)
        
        # 保存整合后的摘要，便于调试
        self._save_text("combined_summary", combined_summary, suffix="_summary.txt")

        final_report = self._generate_report_for_chunk(combined_summary, is_summary=False)
        return final_report

    def run(self, video_url: str):
        """执行主分析流程"""
        print(f"=== 开始分析视频: {video_url} ===")
        try:
            transcript = self._extract_subtitle(video_url)
            print(f"字幕提取成功，长度: {len(transcript)} 字符。")
            
            if self.config.get('output', {}).get('save_subtitles'):
                self._save_text(video_url, transcript, suffix="_raw_transcript.txt")

            report = self._process_long_transcript(transcript)
            
            report_format = self.config.get('output', {}).get('format', 'md')
            report_path = self._save_text(video_url, report, suffix=f"_report.{report_format}")
            
            print("\n" + "="*30)
            print("✅ 报告生成成功！")
            print(f"📄 文件路径: {report_path}")
            print("="*30 + "\n")
            print("--- 报告预览 ---")
            print(report[:400] + "..." if len(report) > 400 else report)

        except (RuntimeError, ValueError) as e:
            print(f"\n❌ 任务失败: {e}")

    def _save_text(self, identifier: str, content: str, suffix: str) -> Path:
        """保存文本内容到文件"""
        if "http" in identifier:
            match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', identifier)
            video_id = match.group(1) if match else "unknown_video"
        else:
            video_id = identifier
            
        filename = f"{video_id}{suffix}"
        path = self.reports_dir / filename
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='YouTube AI 报告生成器 (重构版)',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('url', help='YouTube 视频链接')
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    parser.add_argument(
        '--api-key', 
        help='LLM API Key。\n优先级: 此参数 > 环境变量(LLM_API_KEY) > 配置文件 > 手动输入'
    )
    args = parser.parse_args()

    analyzer = YouTubeAnalyzer(config_path=args.config, api_key=args.api_key)
    analyzer.run(args.url)

if __name__ == "__main__":
    main()
