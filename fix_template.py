# Fix the template file
with open('scripts/dashboard_template_fixed.html', 'r') as f:
    template = f.read()

# Fix the specific line: html += `<td>${v}</td>`;
# Need to escape the JavaScript template literal: ${v} -> ${{v}}
template = template.replace('html += `${v}</td>`;', 'html += `${{v}}</td>`;')

with open('scripts/dashboard_template_fixed.html', 'w') as f:
    f.write(template)

print('Fixed template')