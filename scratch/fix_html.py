import os

def fix_file(path, js_name):
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    html = html.replace(f"filename='js/{js_name}') }}}}", f"filename='js/{js_name}') }}}}?v=2")
    html = html.replace(f"?v=2?v=2", "?v=2") # Just in case
    html = html.replace("}}?v=2 }}", "}}?v=2")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

fix_file('fintech/templates/canslim.html', 'canslim.js')
fix_file('fintech/templates/trend_following.html', 'trend_following.js')
fix_file('fintech/templates/derivatives.html', 'derivatives.js')

