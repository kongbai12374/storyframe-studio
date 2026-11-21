# 公网 HTTPS 配置

适用应用版本 `adbb539`。

`https://studio.example.com/` 为示例地址，并非本仓库提供的在线服务。请使用自己控制的域名或可申请可信证书的公网地址。

## 平台登录认证

`nginx/public-https.conf` 关闭 Nginx HTTP Basic 入口验证，浏览器可直接打开平台登录页，不再弹出额外的账号密码窗口。业务访问使用平台自身的 Session 登录认证。

登录页与前端静态资源可匿名加载。业务 API、素材库和成片下载要求平台会话与对象权限。已开放公网后台的站点由 Django 管理员登录保护。2026-11-21 的部署探测中，匿名访问 `/admin/` 跳转到后台登录，`/health/` 在公网返回 `403`。后台和健康检查的可达性由站点配置决定。

供应商通过 `/api/asset-links/` 读取指定参考素材。接口验证签名、约一小时有效期及素材归属。Nginx 为这条路径配置专用代理，访问日志中避免留下有效签名。

## 证书

为自己的域名配置受信任的证书，修改 Nginx 中的 `ssl_certificate`、`ssl_certificate_key` 与 `server_name`。仓库中的 `drama-ip` 路径只是既有证书名称示例，需要按实际证书路径调整。

如使用 `scripts/drama-cert-renew.service` 和对应 timer，请检查 Certbot 安装路径、证书名称和续期命令。配置完成后执行模拟续期，确认 Nginx 检查和重新加载成功。

HTTP-01 校验使用 `nginx/acme-challenge.conf` 提供挑战路径，保证相应端口和校验目录可达。保留其他已有站点，避免覆盖默认配置。

## 应用配置

- 将实际域名加入 Compose 中的 `ALLOWED_HOSTS` 与 `CSRF_TRUSTED_ORIGINS`。
- `.env` 中设置 `HTTPS_ENABLED=true`，将 `PUBLIC_ORIGIN` 配成实际 HTTPS 地址。
- API 代理设置可信的 `X-Forwarded-Proto=https`。后端只监听回环地址，不直接暴露公网。
- 确认 HTTPS 会话与 CSRF Cookie 带有 Secure 属性。

配置后先执行 `nginx -t`，再重新加载 Nginx。验证匿名访问登录页返回200且不带 `WWW-Authenticate` 挑战；未登录访问业务 API、素材和成片下载被拒绝；平台登录后可正常访问，退出后再次被拒绝；证书可信。不要依赖忽略证书错误来解决部署问题。

生产证书、私钥、管理员口令和供应商密钥由部署者设置。登录页显示的公开演示账号用于体验示例内容。[上线检查与备份](deployment-guide.md)
