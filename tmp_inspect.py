with open('web/assets/app.js') as f:
    content = f.read()
urls = []
for line in content.splitlines():
    for part in line.split('"'):
        if '/api/' in part:
            urls.append(part.split('"')[0] if '"' in part else part)
for url in sorted(set(urls))[:20]:
    print(url)
