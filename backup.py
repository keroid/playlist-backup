# -*- coding: utf-8 -*-
"""
网易云音乐歌单备份脚本
支持公开和私密歌单的备份
"""

import requests
import os
import json
import configparser
import hashlib
from pathlib import Path
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from base64 import b64encode
import binascii
import random
import string


class NeteaseMusicBackup:
    def __init__(self, config_file='config.ini'):
        """初始化配置和会话"""
        self.config = configparser.ConfigParser()
        self.config.read(config_file, encoding='utf-8')

        self.email = self.config.get('netease', 'email')
        self.password = self.config.get('netease', 'password')
        self.download_cover = self.config.getboolean('backup', 'download_cover', fallback=True)
        self.save_path = self.config.get('backup', 'save_path', fallback='./playlists')

        self.session = requests.Session()
        self.user_id = None
        self.cookies = {}

        # 加密密钥 (网易云音乐的固定密钥)
        self.public_key = "010001"
        self.modulus = "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
        self.nonce = "0CoJUm6Qyw8W8jud"
        self.iv = "0102030405060708"

        # API 基础URL
        self.base_url = 'https://music.163.com'
        self.weapi_url = 'https://music.163.com/weapi'

    def _random_text(self, length=16):
        """生成随机字符串"""
        return ''.join(random.sample(string.ascii_letters + string.digits, length))

    def _rsa_encrypt(self, text, pubKey, modulus):
        """RSA加密"""
        text = text[::-1]
        rs = int(binascii.hexlify(text.encode('utf-8')), 16)
        pubKey = int(pubKey, 16)
        modulus = int(modulus, 16)
        cripto = pow(rs, pubKey, modulus)
        return format(cripto, 'x').zfill(256)

    def _aes_encrypt(self, text, key, iv):
        """AES加密"""
        pad_pkcs7 = pad(text.encode('utf-8'), AES.block_size)
        encryptor = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
        encrypted_text = encryptor.encrypt(pad_pkcs7)
        return b64encode(encrypted_text).decode('utf-8')

    def _get_encrypted_params(self, data):
        """
        加密参数 (完整版，支持网易云音乐的AES+RSA加密)
        """
        # 第一次AES加密
        first_key = self.nonce
        first_iv = self.iv
        first_encrypted = self._aes_encrypt(data, first_key, first_iv)

        # 第二次AES加密
        second_key = self._random_text(16)
        second_iv = self.iv
        second_encrypted = self._aes_encrypt(first_encrypted, second_key, second_iv)

        # RSA加密second_key
        rsa_encrypted = self._rsa_encrypt(second_key, self.public_key, self.modulus)

        return {
            'params': second_encrypted,
            'encSecKey': rsa_encrypted
        }
    
    def login(self):
        """登录网易云音乐"""
        print('正在登录网易云音乐...')
        
        # 使用手机号登录的API
        url = f'{self.weapi_url}/login'
        
        # 密码加密 (简化处理)
        data = {
            'username': self.email,
            'password': hashlib.md5(self.password.encode()).hexdigest(),
            'rememberLogin': 'true'
        }
        
        # 使用 encrypted-params 请求
        encrypted_data = self._get_encrypted_params(json.dumps(data))
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://music.163.com/'
            }
            
            response = self.session.post(
                url,
                headers=headers,
                data=encrypted_data
            )
            
            result = response.json()
            
            if result.get('code') == 200:
                self.user_id = result['account']['id']
                self.cookies = response.cookies
                print(f'登录成功！用户ID: {self.user_id}')
                return True
            else:
                print(f'登录失败: {result.get("message", "未知错误")}')
                return False
                
        except Exception as e:
            print(f'登录异常: {str(e)}')
            return False
    
    def get_user_playlists(self, limit=50, offset=0):
        """获取用户的歌单列表（包括私密歌单）"""
        print(f'正在获取歌单列表...')
        
        url = f'{self.weapi_url}/user/playlist'
        
        data = {
            'uid': self.user_id,
            'limit': limit,
            'offset': offset
        }
        
        encrypted_data = self._get_encrypted_params(json.dumps(data))
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://music.163.com/',
            'Cookie': '; '.join([f'{k}={v}' for k, v in self.cookies.items()])
        }
        
        try:
            response = self.session.post(url, headers=headers, data=encrypted_data)
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
        url = f'{self.weapi_url}/v3/playlist/detail'
        
        data = {
            'id': playlist_id,
            'n': 1000
        }
        
        encrypted_data = self._get_encrypted_params(json.dumps(data))
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://music.163.com/',
            'Cookie': '; '.join([f'{k}={v}' for k, v in self.cookies.items()])
        }
        
        try:
            response = self.session.post(url, headers=headers, data=encrypted_data)
            result = response.json()
            
            if result.get('code') == 200:
                return result.get('playlist')
            else:
                print(f'获取歌单详情失败: {result.get("message", "未知错误")}')
                return None
                
        except Exception as e:
            print(f'获取歌单详情异常: {str(e)}')
            return None
    
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
        # 登录
        if not self.login():
            print('登录失败，无法继续')
            return
        
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
