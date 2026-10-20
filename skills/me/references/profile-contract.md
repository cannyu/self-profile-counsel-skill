# 人物画像数据契约

本文件定义 `/me` 的 Skill 与人物数据分离契约。机器可读规则位于
[`profile.contract.json`](profile.contract.json)，可用以下命令校验：

```bash
python3 scripts/validate_profile.py \
  --profile-root "${PERSONA_PROFILE_ROOT:-$HOME/workspace/人物画像}"
```

## 文件职责

- `profile.index.json`：V3 模块、子模块与 legacy source 的机器路由。
- `modules/`：九个 V3 内容模块及健康子模块。
- `evidence/ledger.json`：新事实、偏好、目标、约束、决定和推测。
- `views/`：从模块派生的状态、风险和迁移视图，不是独立事实源。
- `modules/_sources/`：迁移后的原始来源文档，只读保留事实和追溯关系。
- `建议总览.md`：当前优先级，不保存所有历史建议。
- `行动清单.md`：当前动作，不代替事实档案。
- `更新日志.md`：目录级变更记录。
- `历史分析/`、`历史归档/`：只用于追溯，默认不作为当前事实。

九模块为：

1. `identity_context`
2. `goals_values`
3. `health_wellbeing`
4. `capability_growth`
5. `work_career`
6. `finance_resources`
7. `relationships_care`
8. `behavior_psychology`
9. `timeline_actions`

`health_wellbeing` 必须包含 `physical`、`mental`、`sleep_energy`、
`lifestyle` 和 `care_management`。

迁移完成后，事实只在一处维护：模块文档定义结构与摘要，`source_documents`
保存详细来源；不得把同一事实复制到多个模块。

## 信息层级

写入前必须区分以下层级：

| 层级 | 含义 | 默认用法 |
| --- | --- | --- |
| 已确认事实 | 用户确认或有可靠来源 | 可以作为判断依据 |
| 本人判断 | 本人对事实的解释或预判 | 可以使用，但必须注明是判断 |
| 自我叙事 | 本人如何描述自己 | 待检验材料，不得直接当事实 |
| AI 推测 | Agent 基于有限信息提出 | 必须标为假设，不能静默写入事实层 |
| 待确认 | 来源冲突、缺失或尚未确认 | 不得当作最终结论 |
| 历史归档 | 旧版本和不再有效的材料 | 仅在追溯时读取 |

无法确认的信息使用 `❓`，并在对应专项档案的「待确认」部分保留问题。

## 元数据

画像正文使用 YAML frontmatter，至少包含：

- `last_updated`：`YYYY-MM-DD`。
- `version`：形如 `1.0` 或 `v2.0`。
- `visibility`：必须明确本地范围和禁止外传边界。

专项档案还必须包含 `purpose` 和 `source`，用于说明该文件的单一职责与事实来源。

## 更新规则

1. 用户明确确认的稳定事实可以直接更新对应文件。
2. AI 推测、性格判断和重大结论改为候选条目，先说明证据和不确定性，再等待确认。
3. 来源冲突时保留冲突，不得只保留更有利或更顺畅的版本。
4. 修改重大结论时保留旧版本或变更日志，不静默覆盖。
5. 新事实、偏好、目标、约束和推测写入 `evidence/ledger.json`，并同步相关模块摘要。
6. `source_documents` 和 compatibility/partial 模块中的 legacy source 默认只读。
7. 更新后追加 `更新日志.md`；影响长期约束时同步更新派生视图。
8. 删除或外传敏感内容需要用户明确授权，不能从普通分析请求中推断。

## V3 记录

每条 evidence record 至少包含：

- `id`
- `module` 与 `submodule`
- `type`：fact、preference、goal、constraint、event、decision、action、
  self_report、self_narrative、inference 或 source_document
- `statement`
- `source`
- `observed_at` 与 `last_verified`
- `status`：已确认、待确认、冲突、已过期、不采用
- `confidence` 与 `sensitivity`
- `allowed_uses`
- `linked_modules`
- `boundary`

建议和派生的当前状态不能写成 fact。

## 隐私边界

- 完整画像只保存在本地。
- 不将联系方式、体检、家庭、财务或内部工作材料直接发送到外部服务。
- 回答中只复述解决问题所需的最少个人信息。
- 第三方模板、简历 PDF 和原始资料继续由 `.gitignore` 排除。

## 回归用例

[`tests/behavior-cases.json`](../tests/behavior-cases.json) 保存 10—20 条路由与行为契约，
覆盖触发/拒绝、证据分层、更新确认、冲突、时效、隐私和高风险边界。
这些用例当前用于人工检查或 Agent Eval，不自动调用模型。
