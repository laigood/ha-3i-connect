# 3irobotix Robot (F1 Pro)

Unofficial Home Assistant integration for robots on the 3irobotix AllInOne cloud (tested target: F1 Pro, `sweeperDM2F1Pro`).

Status: experimental. Login currently fails with `签名错误-sign` (code 889) because the request signing recipe is not confirmed yet.

Enable debug logs:

```yaml
logger:
  logs:
    custom_components.threei_robot: debug
```
