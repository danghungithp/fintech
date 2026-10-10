import re

path = 'fintech/static/css/app.css'
with open(path, 'rb') as f:
    content = f.read()

# The file might have null bytes now because of UTF-16
# Let's clean it up
# Replace null bytes
content = content.replace(b'\x00', b'')

# Convert to string
text = content.decode('utf-8', errors='ignore')

# Remove the incorrectly appended text
text = re.sub(r'\.module-state.*', '', text, flags=re.DOTALL)

# Append the correct CSS
correct_css = """
.module-state .mod-loading, .module-state .mod-error, .module-state .mod-body { display: none; }
.mod-loading-state .mod-loading { display: block !important; }
.mod-error-state .mod-error { display: block !important; }
.mod-body-state .mod-body { display: block !important; }
"""

text += correct_css

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

