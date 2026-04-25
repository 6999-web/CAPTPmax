import requests, os, json

# 配置
BASE_URL = 'http://127.0.0.1:16063'
image_path = r'C:\Users\xxzx-admin\Desktop\img_v3_0210f_8c427f1f-68a7-43ba-9106-c2b8db3be4ag.jpg'
video_path = r'C:\Users\xxzx-admin\Desktop\test_video.mp4'  # 假设有一个测试视频，如果不存在会报错

def test_image():
    if not os.path.exists(image_path):
        print('Image file not found, skipping image test')
        return
    with open(image_path, 'rb') as f:
        files = {'file': ('target.jpg', f, 'image/jpeg')}
        data = {'mode': 'SHOOTING_TARGET'}
        r = requests.post(f'{BASE_URL}/api/analyze-vision', files=files, data=data)
        print('Image response status:', r.status_code)
        print('Body:', r.text)

def test_video():
    if not os.path.exists(video_path):
        print('Video file not found, skipping video test')
        return
    with open(video_path, 'rb') as f:
        files = {'file': ('sample.mp4', f, 'video/mp4')}
        data = {'mode': 'COMBAT_FIGHT'}
        r = requests.post(f'{BASE_URL}/api/analyze-vision', files=files, data=data)
        print('Video response status:', r.status_code)
        print('Body:', r.text)

if __name__ == '__main__':
    test_image()
    test_video()
