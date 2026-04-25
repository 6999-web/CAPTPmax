import os
import requests, json

BASE_URL = 'http://127.0.0.1:16063'
image_path = r'C:\\Users\\xxzx-admin\\Desktop\\img_v3_0210f_8c427f1f-68a7-43ba-9106-c2b8db3be4ag.jpg'

def test_image():
    try:
        if not os.path.exists(image_path):
            print('Image file not found, skipping image test')
            return
        with open(image_path, 'rb') as f:
            files = {'file': ('target.jpg', f, 'image/jpeg')}
            data = {'mode': 'SHOOTING_TARGET'}
            r = requests.post(f'{BASE_URL}/api/analyze-vision', files=files, data=data, timeout=20)
            print('Status:', r.status_code)
            print('Response:', r.text[:500])
    except Exception as e:
        print('Error during request:', e)

if __name__ == '__main__':
    test_image()
