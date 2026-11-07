# 公网 HTTPS 配置

`https://studio.example.com/` 为示例地址，并非本仓库提供的在线服务。请使用自己控制的域名或可申请可信证书的公网地址。

## 入口认证与平台认证

`nginx/public-https.conf` 展示了两层认证：Nginx 的入口密码，以及平台的用户账号。使用独立生成的强密码，入口密码文件仅保存于服务器，不进入仓库。

除短期签名素材接口外，前端、API、后台和素材下载都应受到相应认证保护。签名素材接口关闭入口密码校验，以便供应商读取，但仍必须验证签名、时效与素材归属，不能公开整个素材目录。

## 证书

为自己的域名配置受信任的证书，修改 Nginx 中的 `ssl_certificate`、`ssl_certificate_key` 与 `server_name`。仓库中的 `drama-ip` 路径只是既有证书名称示例，需要按实际证书路径调整。

如使用 `scripts/drama-cert-renew.service` 和对应 timer，请检查 Certbot 安装路径、证书名称和续期命令。配置完成后执行模拟续期，确认 Nginx 检查和重新加载成功。

HTTP-01 校验使用 `nginx/acme-challenge.conf` 提供挑战路径，保证相应端口和校验目录可达。保留其他已有站点，避免覆盖默认配置。

## 应用配置

- 将实际域名加入 Compose 中的 `ALLOWED_HOSTS` 与 `CSRF_TRUSTED_ORIGINS`。
- `.env` 中设置 `HTTPS_ENABLED=true`，将 `PUBLIC_ORIGIN` 配成实际 HTTPS 地址。
- API 代理设置可信的 `X-Forwarded-Proto=https`。后端只监听回环地址，不直接暴露公网。
- 确认 HTTPS 会话与 CSRF Cookie 带有 Secure 属性。

配置后先执行 `nginx -t`，再重新加载 Nginx。验证匿名入口返回401、授权登录可访问、素材权限正常、证书可信。不要依赖忽略证书错误来解决部署问题。

本仓库不包含可直接使用的证书、私钥、入口账号密码或平台账号密码。
