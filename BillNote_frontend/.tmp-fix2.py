import io
p = r"C:/Users/Administrator/Desktop/prjs/.flow-worktrees/BiliNote/T-062/BillNote_frontend/src/ember/pages/settings/SettingsPage.tsx"
s = io.open(p, encoding='utf-8').read()
start = s.index("            {false && SECTIONS.map(section => (")
end = s.index("            ))}
", s.index("              </NavLink>
", start)) + len("            ))}
")
s = s[:start] + s[end:]
io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('removed', end-start, 'chars')
