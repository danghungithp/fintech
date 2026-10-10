import re

path = 'fintech/templates/base.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the syntax error I just caused
content = content.replace("}}?v=2 }}", "}}?v=2")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

