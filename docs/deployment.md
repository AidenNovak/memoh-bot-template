# 部署与体验

2026-10-01在vultr-sg部署了独立实例，Compose项目 `memoh-template-eval`，目录 `/opt/memoh-template-eval`。服务端和Web均从锁定的上游提交 `1bfb42154e09efacd34f68898ceaab78c10c85f3` 构建，使用独立数据库、containerd命名空间和数据卷。

保留四个演示Bot：芙莉莲、马斯克、阿尼亚、TRPG。已选择聊天模型并收到真实回答，可以在Memoh网页继续聊天、开新会话、调整设置。2026-10-02已单独更新四个Bot的头像，保留现有设置与对话。

同日另建临时Bot完成[八轮实测与修订复测](multiturn-evaluation.md)，共128条新增真实回复。四段复测先在原生网页逐句回读并截图，再删除临时Bot；原始失败和实际回复留在公开报告中。已有四个演示Bot的历史继续保留。

在已配置 `vultr-sg` SSH别名的开发机打开隧道：

```sh
ssh -N -L 12881:127.0.0.1:12880 -L 12883:127.0.0.1:12882 vultr-sg
```

Web：`http://127.0.0.1:12883`；模板选择页使用API：`http://127.0.0.1:12881`。管理员用户名 `admin`，密码沿用本人的Memoh联调私有配置；不在公开仓库提供值。已有本机凭据位置 `~/.config/memoh-ios/dev.env`，服务器私有配置位置 `/opt/memoh-template-eval/eval.env`。

服务仅绑定服务器loopback。server上限2GiB/2CPU，channel768MiB/1CPU，两个数据库各512MiB/1CPU，Web192MiB/0.5CPU；演示Bot工作区分别配置0.5CPU/512MiB/5GiB。构建使用既有6GiB/4CPU限额入口，重任务顺序运行。没有改动现有Memoh dev或生产服务。

以下运维脚本针对该开发环境，不是任意服务器的一键安装器：

```sh
# 仅在vultr-sg执行，先构建再部署
bash ops/build_eval_image.sh
python3 ops/deploy_eval.py
python3 ops/configure_eval_models.py
python3 ops/seed_eval_demos.py
# 仅更新已存在的四个演示Bot头像，先保存私有备份
python3 ops/update_demo_avatars.py
```

模型初始化脚本只在服务器内读取原dev配置，因为Provider API会隐藏密钥，读取其数据库中的原配置后写入独立评估库。凭据不经本机、不输出、不进入Git。首次构建脚本锁定提交且使用全新镜像标签；已构建时不必重复构建。

状态检查：

```sh
ssh vultr-sg 'docker compose -f /opt/memoh-template-eval/compose.json ps'
```

关闭独立实例可以在服务器执行对应compose的 `down`，默认保留数据卷。不要关闭其他项目的服务。
