import re

path = 'fintech/static/js/app.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

showState_code = """
  function showState(modId, state) {
    const root = document.getElementById(modId);
    if (!root) return;
    root.classList.remove('mod-loading-state', 'mod-error-state', 'mod-body-state');
    if (state) root.classList.add(`mod-${state}-state`);
  }
"""

if 'function showState' not in content:
    # insert before window.App = ...
    content = content.replace("window.App =", showState_code + "\n  window.App =")
    
    # export it
    content = content.replace("window.App = {", "window.App = { showState,")
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched app.js")
else:
    print("Already patched")

