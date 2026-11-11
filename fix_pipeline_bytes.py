with open(r'E:\resipsc v2 final 1\resipsc\training\v3_pipeline.py', 'rb') as f:
    content = f.read()

# Replace escaped triple quotes
content = content.replace(b'\\\\"\\\\"\\\\"', b'"""')
content = content.replace(b'\\"\\"\\"', b'"""')

with open(r'E:\resipsc v2 final 1\resipsc\training\v3_pipeline.py', 'wb') as f:
    f.write(content)

print('Fixed v3_pipeline.py bytes')