# Self Profile Counsel Skill

一个把可复用人物画像工作流与私有个人数据分离的 Codex 插件。

An agent skill that incrementally builds an evolving self-profile and provides
personal decisions, small decision support, growth suggestions, and privacy-aware
profile maintenance. Integration with cost-effective life guidance is planned.

插件提供：

- `/me` 个人决策 Skill。
- 人物画像数据结构与数据契约。
- 九个内容模块、健康子模块与证据账本。
- 更新、审计和脱敏导出的行为规则。
- 离线结构校验器。
- 基于虚构档案的路由与隐私回归测试。

个人画像、联系方式、健康、家庭和财务资料不应放入本仓库。

## 目录

```text
persona-profile-skill/
├── .codex-plugin/plugin.json
├── skills/me/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/
│   ├── scripts/
│   └── tests/
├── README.md
└── LICENSE
```

## 使用

将本仓库放在本地 marketplace 的插件目录中，并确保对应 marketplace 已注册：

```bash
codex plugin marketplace add /path/to/marketplace-root
codex plugin add persona-profile-skill@workspace-plugins
```

画像数据独立存放，通过环境变量指定：

```bash
export PERSONA_PROFILE_ROOT="$HOME/workspace/人物画像"
```

未设置环境变量时，校验器使用：

```text
$HOME/workspace/人物画像
```

也可以为单次校验显式传入路径：

```bash
python3 skills/me/scripts/validate_profile.py \
  --profile-root "$HOME/workspace/人物画像"
```

## 数据契约

- `profile.index.json`：模块、子模块和兼容来源路由。
- 九个内容模块：身份、目标价值、身心健康、能力成长、工作职业、财务资源、关系照护、行为心理和时间线行动。
- 身心健康包含身体、心理、睡眠精力、生活方式和健康管理。
- `evidence/ledger.json`：新事实、偏好、目标、约束、决定和推测。
- `views/`：从模块派生的状态、风险和迁移视图。
- 事实、用户判断、AI 推测和待确认信息必须分开。
- 历史归档只用于追溯，不作为当前事实。

详细规则见
[`skills/me/references/profile-contract.md`](skills/me/references/profile-contract.md)。

## 开发与测试

```bash
python3 -m unittest discover -s skills/me/tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py skills/me
```

仓库测试只使用
[`skills/me/tests/fixtures/valid-profile/`](skills/me/tests/fixtures/valid-profile/)
中的虚构数据，不读取真实个人档案。

## 隐私

- 默认仅在本地读取画像。
- 不将个人档案提交到本仓库。
- 不把联系方式、医疗、家庭、财务或内部工作材料发送到外部服务。
- 导出或外部分享前只保留用户指定范围，并执行脱敏。

## License

MIT
