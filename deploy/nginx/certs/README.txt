# OfficeAgent nginx SSL 证书目录
#
# 部署时需放入以下文件:
#   - fullchain.pem   证书链(含中间证书)
#   - privkey.pem     私钥
#
# 开发环境生成自签证书:
#   openssl req -x509 -newkey rsa:2048 -nodes -keyout privkey.pem \
#     -out fullchain.pem -days 365 -subj "/CN=localhost" \
#     -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
#
# 生产环境使用 Let's Encrypt:
#   certbot certonly --webroot -w /var/www/certbot -d officeagent.example.com
#   然后将 /etc/letsencrypt/live/<domain>/{fullchain,privkey}.pem 软链或复制到本目录
