with open(r'E:\resipsc v2 final 1\resipsc\training\v3_pipeline.py', 'r', encoding='utf-8-sig') as f:
    content = f.read()

content = content.replace('\\"""', '"""')

with open(r'E:\resipsc v2 final 1\resipsc\training\v3_pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed v3_pipeline.py')