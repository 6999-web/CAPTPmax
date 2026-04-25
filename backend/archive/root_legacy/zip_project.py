import os
import zipfile

def zip_project(output_filename, source_dir):
    # 要排除的文件夹与后缀
    exclude_dirs = {'.git', 'node_modules', 'captp_env', '__pycache__', 'dist', '.vscode', '.idea'}
    exclude_files = {'.DS_Store', 'Thumbs.db', 'test_keys.py', 'test_keys2.py', 'backend/config.py'}
    
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # 原地修改 dirs 以便 os.walk 会递归排除这些目录
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, source_dir)
                
                # 检查是否为被排除的文件
                if rel_path in exclude_files or any(rel_path.endswith(ext) for ext in {'.pyc', '.pyo', '.pyd', '.log'}):
                    continue
                
                print(f"Adding: {rel_path}")
                zipf.write(file_path, rel_path)

if __name__ == "__main__":
    current_dir = os.getcwd()
    output_zip = os.path.join(current_dir, "CAPTP_Source_Project.zip")
    zip_project(output_zip, current_dir)
    print(f"\n--- SUCCESS ---")
    print(f"Project zipped to: {output_zip}")
