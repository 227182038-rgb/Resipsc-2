import os

def fix_file(filepath):
    """Fix BOM and escaped triple quotes in a Python file."""
    with open(filepath, 'rb') as f:
        content = f.read()

    # Remove BOM if present
    if content.startswith(b'\xef\xbb\xbf'):
        content = content[3:]

    # Fix escaped triple quotes
    content = content.replace(b'\\\\"\\\\"\\\\"', b'"""')
    content = content.replace(b'\\"\\"\\"', b'"""')

    with open(filepath, 'wb') as f:
        f.write(content)

# Fix all Python files in the resipsc directory
root = r'E:\resipsc v2 final 1\resipsc'
for dirpath, dirnames, filenames in os.walk(root):
    for fname in filenames:
        if fname.endswith('.py'):
            fix_file(os.path.join(dirpath, fname))

# Fix scripts
scripts_root = r'E:\resipsc v2 final 1\scripts'
for fname in os.listdir(scripts_root):
    if fname.endswith('.py'):
        fix_file(os.path.join(scripts_root, fname))

# Fix src
src_root = r'E:\resipsc v2 final 1\src'
for dirpath, dirnames, filenames in os.walk(src_root):
    for fname in filenames:
        if fname.endswith('.py'):
            fix_file(os.path.join(dirpath, fname))

print('Fixed all Python files')