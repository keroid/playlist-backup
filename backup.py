# -*- coding: utf-8 -*-
"""
网易云音乐歌单备份脚本
支持公开和私密歌单的备份
使用 https://apis.netstart.cn/music API
"""

import requests
import os
import json
import configparser
import hashlib

class NeteaseMusicBackup:
    def __init__(self, config_file='config.ini'):
        """初始化配置和会话"""
        self.config = configparser.ConfigParser(interpolation=None)
        self.config.read(config_file, encoding='utf-8')

        # 从配置读取Cookie
        self.cookie_str = self.config.get('netease', 'cookie', fallback='')
        self.download_cover = self.config.getboolean('backup', 'download_cover', fallback=True)
        self.save_path = self.config.get('backup', 'save_path', fallback='./playlists')

        self.session = requests.Session()
        self.user_id = None

        # API 基础URL
        self.api_url = 'https://apis.netstart.cn/music'

    def get_user_id(self):
        """从API获取用户ID"""
        url = f'{self.api_url}/user/account'

        headers = self._get_headers()

        try:
            response = self.session.get(url, headers=headers)
            result = response.json()

            if result.get('code') == 200 and result.get('profile'):
                return result['profile']['userId']
            return None
        except Exception as e:
            print(f'获取用户ID异常: {str(e)}')
            return None

    def get_user_playlists(self, limit=50, offset=0):
        """获取用户的歌单列表（包括私密歌单）"""
        print(f'正在获取歌单列表...')

        url = f'{self.api_url}/user/playlist'
        params = {
            'uid': self.user_id,
            'limit': limit,
            'offset': offset
        }

        headers = self._get_headers()

        try:
            response = self.session.get(url, headers=headers, params=params)
            result = response.json()

            if result.get('code') == 200:
                playlists = result.get('playlist', [])
                print(f'共找到 {len(playlists)} 个歌单')
                return playlists
            else:
                print(f'获取歌单失败: {result.get("message", "未知错误")}')
                return []

        except Exception as e:
            print(f'获取歌单异常: {str(e)}')
            return []

    def get_playlist_detail(self, playlist_id):
        """获取歌单详情（包括歌曲信息）"""
        url = f'{self.api_url}/playlist/detail'
        params = {
            'id': playlist_id
        }

        headers = self._get_headers()

        try:
            response = self.session.get(url, headers=headers, params=params)
            result = response.json()

            if result.get('code') == 200:
                return result.get('playlist')
            else:
                print(f'获取歌单详情失败: {result.get("message", "未知错误")}')
                return None

        except Exception as e:
            print(f'获取歌单详情异常: {str(e)}')
            return None

    def _get_headers(self):
        """构建请求头"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://music.163.com/'
        }

        # 如果有Cookie，添加到请求头
        if self.cookie_str:
            headers['Cookie'] = self.cookie_str

        return headers
    
    def download_cover(self, cover_url, save_dir):
        """下载封面图片"""
        if not self.download_cover or not cover_url:
            return None
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://music.163.com/'
            }
            
            response = self.session.get(cover_url, headers=headers)
            
            if response.status_code == 200:
                # 使用MD5作为文件名避免重复下载
                filename = hashlib.md5(cover_url.encode()).hexdigest() + '.jpg'
                filepath = os.path.join(save_dir, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                return filename
            return None
            
        except Exception as e:
            print(f'下载封面失败: {str(e)}')
            return None
    
    def backup_playlist(self, playlist):
        """备份单个歌单"""
        playlist_id = playlist['id']
        playlist_name = playlist['name']
        playlist_description = playlist.get('description', '')
        playlist_cover = playlist.get('coverImgUrl', '')
        
        print(f'\n正在备份歌单: {playlist_name}')
        print(f'歌单ID: {playlist_id}')
        
        # 获取歌单详情
        detail = self.get_playlist_detail(playlist_id)
        if not detail:
            print(f'获取歌单详情失败')
            return None
        
        # 创建保存目录
        safe_name = ''.join(c for c in playlist_name if c.isalnum() or c in (' ', '-', '_')).strip()
        playlist_dir = os.path.join(self.save_path, safe_name)
        os.makedirs(playlist_dir, exist_ok=True)
        
        # 下载封面
        cover_filename = self.download_cover(playlist_cover, playlist_dir)
        
        # 提取歌曲信息
        tracks = detail.get('tracks', [])
        songs = []
        
        for idx, track in enumerate(tracks, 1):
            song_info = {
                'id': track['id'],
                'name': track['name'],
                'artist': ', '.join([ar['name'] for ar in track['ar']]),
                'album': track['al']['name'],
                'url': f"https://music.163.com/#/song?id={track['id']}",
                'order': idx
            }
            songs.append(song_info)
            print(f'  {idx}. {song_info["name"]} - {song_info["artist"]}')
        
        # 构建备份数据
        backup_data = {
            'playlist_id': playlist_id,
            'name': playlist_name,
            'description': playlist_description,
            'cover_url': playlist_cover,
            'cover_file': cover_filename,
            'song_count': len(songs),
            'created_time': playlist.get('createTime', ''),
            'updated_time': playlist.get('updateTime', ''),
            'privacy': playlist.get('privacy', 0),  # 0:公开, 10:私密
            'songs': songs
        }
        
        # 保存为JSON文件
        json_file = os.path.join(playlist_dir, 'playlist.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        # 同时保存为易读的文本文件
        txt_file = os.path.join(playlist_dir, 'playlist.txt')
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"歌单名称: {playlist_name}\n")
            f.write(f"歌单ID: {playlist_id}\n")
            f.write(f"简介: {playlist_description}\n")
            f.write(f"歌曲数量: {len(songs)}\n")
            f.write(f"创建时间: {playlist.get('createTime', '')}\n")
            f.write(f"更新时间: {playlist.get('updateTime', '')}\n")
            f.write(f"隐私设置: {'私密' if playlist.get('privacy') == 10 else '公开'}\n")
            f.write(f"封面: {cover_filename if cover_filename else '未下载'}\n")
            f.write("\n" + "="*50 + "\n")
            f.write("歌曲列表:\n\n")
            
            for song in songs:
                f.write(f"{song['order']}. {song['name']} - {song['artist']}\n")
                f.write(f"   专辑: {song['album']}\n")
                f.write(f"   URL: {song['url']}\n\n")
        
        print(f'备份完成！已保存到: {playlist_dir}')
        return backup_data
    
    def backup_all(self):
        """备份所有歌单"""
        # 检查Cookie
        if not self.cookie_str:
            print('错误：请在config.ini中配置cookie')
            print('私密歌单需要Cookie才能访问')
            return

        # 获取用户ID
        print('正在获取用户信息...')
        self.user_id = self.get_user_id()
        if not self.user_id:
            print('无法获取用户ID，请检查Cookie是否有效')
            return
        print(f'用户ID: {self.user_id}')

        # 创建保存目录
        os.makedirs(self.save_path, exist_ok=True)

        # 获取所有歌单
        playlists = self.get_user_playlists()
        if not playlists:
            print('未找到任何歌单')
            return

        # 分备份
        backup_results = []

        for playlist in playlists:
            try:
                result = self.backup_playlist(playlist)
                if result:
                    backup_results.append(result)
            except Exception as e:
                print(f'备份歌单时出错: {str(e)}')
                continue

        # 生成汇总报告
        summary_file = os.path.join(self.save_path, 'backup_summary.json')
        summary = {
            'user_id': self.user_id,
            'total_playlists': len(backup_results),
            'backup_time': str(os.path.getctime(summary_file) if os.path.exists(summary_file) else ''),
            'playlists': [
                {
                    'name': p['name'],
                    'id': p['playlist_id'],
                    'song_count': p['song_count'],
                    'privacy': p['privacy']
                }
                for p in backup_results
            ]
        }

        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print(f'\n备份完成！')
        print(f'总计备份: {len(backup_results)} 个歌单')
        print(f'保存路径: {os.path.abspath(self.save_path)}')


def main():
    """主函数"""
    # 检查配置文件
    if not os.path.exists('config.ini'):
        print('错误: 未找到配置文件 config.ini')
        print('请先配置 config.ini 文件，填入你的网易云音乐账号信息')
        return
    
    # 创建备份实例
    backup = NeteaseMusicBackup('config.ini')
    
    # 开始备份
    backup.backup_all()


if __name__ == '__main__':
    main()
