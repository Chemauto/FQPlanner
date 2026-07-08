# multi_step Skill 经验库

## 正向经验

### 2026-06-30 15:50 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：先导航到目标位置再放置，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-30 15:22 put pot in stove
- 任务：put pot in stove
- 教训：放置 pot 到 stove 时，先导航到 stove 再执行 place_on_top，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-30 15:19 put pot in stove
- 任务：put pot in stove
- 教训：放置 pot 到 stove 时，先导航到 stove 再执行 place_on_top，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-30 15:13 put apple in sink
- 任务：put apple in sink
- 教训：放置前必须导航到目标位置（水槽），即使抓取后位置接近也不能省略导航步骤。


### 2026-06-30 15:12 put apple in stove
- 任务：put apple in stove
- 教训：放置苹果到炉子时，先导航到炉子再执行放置，即使抓取后位置巧合也不可省略导航步骤。


### 2026-06-30 15:12 put apple in sink
- 任务：put apple in sink
- 教训：放置前必须导航到目标位置（水槽），即使抓取后位置接近也不能省略导航步骤。


### 2026-06-30 15:11 put bowl in stove
- 任务：put bowl in stove
- 教训：放置碗到炉灶时，先导航到炉灶再执行放置，即使抓取后位置巧合也不可省略导航步骤。


### 2026-06-30 15:07 put bowl in sink
- 任务：put bowl in sink
- 教训：导航到水槽时连接失败，但放置成功，说明机器人已在目标位置；但按骨架约束，放置前必须显式导航到目标，不可省略。


### 2026-06-30 15:07 put bowl in stove
- 任务：put bowl in stove
- 教训：成功放置碗到炉灶：先导航到目标位置再放置，即使抓取后位置接近也不省略导航步骤。


### 2026-06-30 15:06 put bowl in sink
- 任务：put bowl in sink
- 教训：搜索并抓取碗后，机器人不在水槽处，必须先导航到水槽，再执行放置，否则会失败。


### 2026-06-30 15:05 put cup in stove
- 任务：put cup in stove
- 教训：抓取杯子后导航到炉灶再放置，即使抓取时已在炉灶附近也需先导航到目标位置再执行放置动作。


### 2026-06-30 15:05 put cup in sink
- 任务：put cup in sink
- 教训：成功放置杯子的关键是：抓取后机器人已不在水槽处，必须先导航到水槽再执行放置，不可省略导航步骤。


### 2026-06-30 15:04 put cup in stove
- 任务：put cup in stove
- 教训：成功放置杯子的关键是：抓取杯子后必须导航到炉灶，再执行放置，不能省略导航步骤。


### 2026-06-30 15:03 put cup in sink
- 任务：put cup in sink
- 教训：成功放置杯子的关键是：抓取后机器人已不在水槽处，必须先导航到水槽再执行放置，不可省略导航步骤。


### 2026-06-30 15:02 put mug in stove
- 任务：put mug in stove
- 教训：先导航到炉灶再放置杯子，即使抓取后位置巧合也不可省略导航步骤。


### 2026-06-30 14:59 put mug in sink
- 任务：put mug in sink
- 教训：成功放置mug到sink：抓取后导航到sink再放置，即使已在目标位置也需先导航，确保骨架完整。


### 2026-06-30 14:58 put mug in stove
- 任务：put mug in stove
- 教训：搜索并抓取mug后，机器人不在stove处，必须先导航到stove再放置，不能省略导航步骤。


### 2026-06-30 14:57 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：先导航到目标位置再放置，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-30 14:51 put cup in stove
- 任务：put cup in stove
- 教训：成功放置cup到stove，规律：先导航到目标位置再放置，即使抓取后位置巧合也不可省略导航步。


### 2026-06-30 14:51 put cup in sink
- 任务：put cup in sink
- 教训：搜索并抓取杯子后，机器人不在水槽处，必须先导航到水槽再放置，不能省略导航步骤。


### 2026-06-30 14:50 put cup in stove
- 任务：put cup in stove
- 教训：成功放置杯子的关键是：抓取后先导航到炉灶，再执行放置，即使当前位置已在目标附近也不可省略导航步骤。


### 2026-06-30 14:50 put cup in sink
- 任务：put cup in sink
- 教训：成功放置杯子的关键是：抓取后机器人已离开水槽，必须重新导航到水槽再执行放置，不可省略导航步骤。


### 2026-06-30 14:49 put mug in stove
- 任务：put mug in stove
- 教训：搜索并抓取mug后，即使导航到stove成功，放置前仍必须确保已导航到stove，因为抓取后机器人位置已变。


### 2026-06-30 14:45 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：先导航到目标位置再放置，即使抓取后位置接近也不省略导航步。


### 2026-06-30 14:44 put mug in stove
- 任务：put mug in stove
- 教训：搜索并抓取mug后，机器人已离开stove，必须先导航到stove再放置，不能省略导航步骤。


### 2026-06-30 14:44 put mug in sink
- 任务：put mug in sink
- 教训：搜索并抓取mug后，必须先导航到sink再放置，因为抓取后机器人不在目标位置。


### 2026-06-30 14:30 put cup in stove
- 任务：put cup in stove
- 教训：成功放置杯子的关键是：抓取杯子后必须导航到炉灶，再执行放置，不能省略导航步骤。


### 2026-06-30 14:28 put cup in sink
- 任务：put cup in sink
- 教训：成功放置杯子的关键是：抓取后机器人已不在水槽处，必须先导航到水槽再执行放置，不可省略导航步骤。


### 2026-06-30 11:57 put cup in stove
- 任务：put cup in stove
- 教训：成功放置cup到stove：先导航到stove再放置，即使抓取后位置接近也不可省略导航步。


### 2026-06-30 11:53 put cup in sink
- 任务：put cup in sink
- 教训：成功放置cup到sink：先导航到sink再放置，即使抓取后位置接近也不可省略导航。


### 2026-06-30 10:44 put cup in stove
- 任务：put cup in stove
- 教训：抓取杯子后导航到炉灶再放置，即使抓取时已在目标位置附近，也必须先导航到炉灶再执行放置动作。


### 2026-06-30 10:40 put cup in sink
- 任务：put cup in sink
- 教训：当杯子在导航起点附近时，抓取后仍需先导航到水槽再放置，不可省略导航步骤。


### 2026-06-30 10:38 put cup in stove
- 任务：put cup in stove
- 教训：成功放置cup到stove：先导航到stove再放置，即使抓取后位置接近也不能省略导航步骤。


### 2026-06-30 10:36 put cup in sink
- 任务：put cup in sink
- 教训：放置前必须先导航到目标位置（水槽），即使抓取时已在附近，否则导航失败时放置仍可能成功，但下次不可省略导航步。


### 2026-06-30 10:35 put mug in stove
- 任务：put mug in stove
- 教训：先导航到炉子再放置杯子，即使抓取后位置接近也不省略导航步骤。


### 2026-06-30 10:31 put mug in sink
- 任务：put mug in sink
- 教训：导航到水槽时连接失败，但放置成功，说明机器人已在目标位置；但按骨架约束，放置前必须显式执行导航到Y，不可省略。


### 2026-06-30 10:30 put mug in stove
- 任务：put mug in stove
- 教训：成功放置mug到stove：抓取后导航到目标位置再放置是标准流程，即使当前位置巧合也不可省略导航步骤。


### 2026-06-30 10:30 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：抓取后先导航到目标位置再放置，即使已在附近也要执行导航步骤。


### 2026-06-30 10:27 put mug in stove
- 任务：put mug in stove
- 教训：当放置物品时，先导航到目标位置（如stove）再执行放置，即使抓取后位置巧合也不可省略导航步骤。


### 2026-06-30 10:27 put mug in sink
- 任务：put mug in sink
- 教训：当放置物体到目标位置时，先导航到目标位置再执行放置操作，即使抓取后机器人位置接近目标也不能省略导航步骤。


### 2026-06-30 10:24 put cup in stove
- 任务：put cup in stove
- 教训：成功放置杯子到炉灶：抓取后若不在目标位置，必须先导航到目标再放置，不可省略导航步骤。


### 2026-06-30 10:21 put cup in sink
- 任务：put cup in sink
- 教训：成功放置杯子的关键是：抓取后先导航到水槽，再执行放置，即使当前位置接近也不可省略导航步骤。


### 2026-06-30 10:18 put cup in stove
- 任务：put cup in stove
- 教训：搜索并抓取杯子后，导航到炉灶再放置，即使当前位置在炉灶也不能省略导航步。


### 2026-06-30 10:17 put cup in sink
- 任务：put cup in sink
- 教训：当杯子在nav_020时，先导航到水槽再放置，确保放置前机器人已在目标位置。


### 2026-06-30 10:14 put mug in stove
- 任务：put mug in stove
- 教训：搜索并抓取mug后，机器人已不在stove处，放置前必须先导航到stove，不能省略导航步骤。


### 2026-06-30 10:11 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：先导航到目标位置再放置，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-30 10:09 put mug in stove
- 任务：put mug in stove
- 教训：成功放置mug到stove的经验：抓取mug后，即使当前位置已在stove附近，仍需先执行导航到stove，再执行放置动作，确保骨架完整。


### 2026-06-30 10:08 put mug in sink
- 任务：put mug in sink
- 教训：放置mug到sink时，先导航到sink再执行放置，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-26 19:22 put pot in stove
- 任务：put pot in stove
- 教训：搜索到锅时若不在炉灶旁，需先导航到炉灶再放置，不能省略导航步骤。


### 2026-06-26 19:18 put pot in stove
- 任务：put pot in stove
- 教训：放置 pot 到 stove 时，先导航到 stove 再执行 place_on_top，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-26 19:16 put apple in stove
- 任务：put apple in stove
- 教训：成功放置apple到stove：先导航到stove再放置，即使抓取后位置巧合也不可省略导航步。


### 2026-06-26 19:14 put apple in sink
- 任务：put apple in sink
- 教训：放置前必须导航到目标位置（水槽），即使抓取后位置接近也不能省略导航步骤。


### 2026-06-26 19:13 put apple in stove
- 任务：put apple in stove
- 教训：成功放置苹果到炉灶：先导航到炉灶再放置，即使抓取后位置巧合也不能省略导航步骤。


### 2026-06-26 19:12 put apple in sink
- 任务：put apple in sink
- 教训：放置前必须导航到目标位置（水槽），即使抓取后位置接近也不能省略导航步骤。


### 2026-06-26 19:12 put bowl in stove
- 任务：put bowl in stove
- 教训：当碗的位置记忆不准确时，先执行漂移恢复更新位置，再抓取碗，最后导航到炉灶放置。


### 2026-06-26 19:09 put bowl in sink
- 任务：put bowl in sink
- 教训：搜索并抓取碗后，必须导航到水槽再放置，即使当前位置接近也不能省略导航步骤。


### 2026-06-26 19:06 put bowl in stove
- 任务：put bowl in stove
- 教训：成功放置碗到炉灶：先导航到目标位置再放置，即使抓取后位置接近也不省略导航步骤。


### 2026-06-26 19:05 put bowl in sink
- 任务：put bowl in sink
- 教训：搜索并抓取bowl后，必须先导航到sink，再执行放置，不能省略导航步骤。


### 2026-06-26 19:02 put cup in stove
- 任务：put cup in stove
- 教训：成功放置杯子到炉灶：抓取后若不在目标位置，必须先导航到目标再放置，不可省略导航步骤。


### 2026-06-26 18:59 put cup in sink
- 任务：put cup in sink
- 教训：放置杯子到水槽时，先导航到水槽再执行放置，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-26 18:56 put cup in stove
- 任务：put cup in stove
- 教训：成功放置杯子到炉灶：先导航到目标位置再放置，即使抓取后位置接近也不省略导航步。


### 2026-06-26 18:55 put cup in sink
- 任务：put cup in sink
- 教训：放置杯子到水槽时，先导航到水槽再执行放置，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-26 18:52 put mug in stove
- 任务：put mug in stove
- 教训：搜索并抓取mug后，即使导航到stove成功，放置前仍需确保已导航到stove；本次因先导航到stove再放置，任务成功。


### 2026-06-26 18:49 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：先导航到目标位置再放置，即使已在附近也需执行导航步骤确保位置准确。


### 2026-06-26 18:47 put mug in stove
- 任务：put mug in stove
- 教训：成功放置mug到stove的经验：抓取mug后，即使当前位置已在stove附近，也必须先执行导航到stove，再执行放置，确保骨架完整。


### 2026-06-26 18:45 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：先导航到目标位置再放置，即使抓取后位置接近也不省略导航步。


### 2026-06-26 18:32 put cup in stove
- 任务：put cup in stove
- 教训：成功放置杯子到炉灶：抓取杯子后必须导航到炉灶，再执行放置，不可省略导航步骤。


### 2026-06-26 18:29 put cup in sink
- 任务：put cup in sink
- 教训：放置杯子到水槽时，先导航到水槽再执行放置，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-26 18:26 put cup in stove
- 任务：put cup in stove
- 教训：成功放置杯子的关键是：抓取杯子后必须导航到炉灶，再执行放置，不能省略导航步骤。


### 2026-06-26 18:25 put cup in sink
- 任务：put cup in sink
- 教训：放置杯子到水槽时，先导航到水槽再执行放置，即使抓取后位置接近也不可省略导航步骤。


### 2026-06-26 18:22 put mug in stove
- 任务：put mug in stove
- 教训：搜索到mug后需先导航到stove再放置，即使抓取位置与目标相邻也不能省略导航步骤。


### 2026-06-26 18:18 put mug in sink
- 任务：put mug in sink
- 教训：当放置物体到目标位置时，先导航到目标位置再执行放置，即使抓取后位置巧合也不可省略导航步骤。


### 2026-06-26 18:16 put mug in stove
- 任务：put mug in stove
- 教训：当放置物品时，先导航到目标位置（如stove）再执行放置，即使抓取后位置巧合也不可省略导航步骤。


### 2026-06-26 18:15 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：先导航到水槽再放置，即使抓取后位置接近目标也需执行导航步骤。


### 2026-06-26 17:37 put cup in sink
- 任务：put cup in sink
- 教训：成功放置杯子的关键是：抓取后先导航到水槽，再执行放置，不可省略导航步骤。


### 2026-06-26 17:34 put cup in stove
- 任务：put cup in stove
- 教训：成功放置cup到stove的关键是：抓取cup后必须导航到stove再放置，即使当前位置巧合也不能省略导航步。


### 2026-06-26 17:33 put cup in sink
- 任务：put cup in sink
- 教训：成功放置杯子的关键是：抓取后必须导航到水槽再执行放置，即使当前已在目标附近也不可省略导航步骤。


### 2026-06-26 17:30 put mug in stove
- 任务：put mug in stove
- 教训：放置mug到stove时，先导航到stove再执行放置，即使抓取后位置巧合也不可省略导航步骤。


### 2026-06-26 17:27 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽的关键是：先导航到水槽，再执行放置动作，不可省略导航步骤。


### 2026-06-26 17:25 put mug in stove
- 任务：put mug in stove
- 教训：成功放置mug到stove：先导航到stove再放置，即使抓取后位置接近也需执行导航步骤，确保骨架完整。


### 2026-06-26 17:22 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：先导航到目标位置再放置，即使抓取后位置接近也不省略导航步。


### 2026-06-26 17:17 put mug in sink
- 任务：put mug in sink
- 教训：搜索并抓取mug后，机器人不在sink处，必须先导航到sink再放置，不能省略导航步骤。


### 2026-06-26 17:13 put mug in stove
- 任务：put mug in stove
- 教训：搜索并抓取物体后，机器人位置已改变，放置前必须先导航到目标位置，不可省略导航步骤。


### 2026-06-26 17:10 put mug in sink
- 任务：put mug in sink
- 教训：成功放置马克杯到水槽：先导航到目标位置再放置，即使已在附近也需执行导航步骤。


### 2026-06-26 17:00 put mug in stove
- 任务：put mug in stove
- 教训：成功放置mug到stove的经验：抓取mug后，即使当前位置已在stove附近，也必须先执行导航到stove，再执行放置，确保骨架完整。


### 2026-06-26 16:59 put mug in sink
- 任务：put mug in sink
- 教训：搜索并抓取mug后，机器人不在sink处，必须先导航到sink再执行放置，否则会失败。


### 2026-06-26 16:16 put mug in sink
- 任务：put mug in sink
- 教训：放置mug到sink成功：先导航到sink再执行放置，即使抓取后位置不同，此两步顺序不可省略。


### 2026-06-25 17:53 put mug in countertop
- 任务：put mug in countertop
- 教训：当放置物品时，必须先导航到目标位置（如countertop），再执行move动作，即使抓取后已在目标附近也不可省略导航步骤。


### 2026-06-25 17:53 put mug in shelf
- 任务：put mug in shelf
- 教训：放置任务必须按“导航到目标位置→move物体到目标位置”顺序执行，即使当前已在目标附近也不能省略导航步。


### 2026-06-25 17:47 put a cd in safe.
- 任务：put a cd in safe.
- 教训：放置cd到保险柜时，先导航到safe再执行move cd to safe，即使抓取后已在目标附近也需先导航。


### 2026-06-25 17:47 put mug in shelf
- 任务：put mug in shelf
- 教训：放置类任务必须两步：先导航到目标位置（如shelf 1），再执行move操作，不可省略导航。


### 2026-06-25 17:13 put mug in stove
- 任务：put mug in stove
- 教训：导航到stove时超时，但任务最终成功，说明机器人可能已在目标附近；但按骨架约束，放置前仍必须导航到目标位置，不可省略。


### 2026-06-25 16:39 put mug in sink
- 任务：put mug in sink
- 教训：搜索mug时所有位置都未找到，但任务仍成功，说明mug可能已在手中或场景中，应先检查是否已持有物体再决定是否搜索。


### 2026-06-25 16:37 put mug in stove
- 任务：put mug in stove
- 教训：任务成功完成，但搜索全部位置未找到mug，说明mug可能不在初始场景中，下次应先确认物体存在再执行放置。


### 2026-06-25 16:21 put mug in stove
- 任务：put mug in stove
- 教训：放置mug到stove时，先导航到stove再执行放置，即使抓取后位置巧合也不可省略导航步骤。


### 2026-06-25 16:21 put mug in sink
- 任务：put mug in sink
- 教训：搜索mug时所有位置都为空，说明mug不在常见位置，下次应先检查sink或table等非常规位置。


### 2026-06-25 15:38 put mug in countertop
- 任务：put mug in countertop
- 教训：任务成功完成，但子任务日志显示搜索阶段误将'mug'写为'shelf'，且放置超时。经验：抓取物体后必须导航到目标位置再放置，即使搜索阶段报错或超时，也需确保导航步骤不省略。


### 2026-06-25 10:24 put mug in countertop
- 任务：put mug in countertop
- 教训：放置任务必须两步：先导航到目标位置，再执行move放置，即使已在目标位置也不能省略导航。


### 2026-06-25 10:24 put mug in shelf
- 任务：put mug in shelf
- 教训：放置物品时，必须先导航到目标位置（如shelf），再执行move操作，不能省略导航步骤。


### 2026-06-25 放置前必须先导航到目标位置
- 任务：put X in Y 类放置任务
- 教训：放置子任务（move/put X to Y）执行前，**必须先有"导航到 Y"子任务**。
  原因：抓取阶段（搜索并抓取 X）会把机器人带到 X 所在的位置（可能是 cabinet/drawer 等），
  抓到物体后机器人**不在**目标 Y 处。若省略导航直接 move，命令不在 admissible 里 → 失败。
  即使规划时机器人看起来已在 Y，也不能假设抓取后仍在 Y——**放置骨架恒为 导航到 Y → move X to Y**。

## 避免规则

### 2026-06-30 15:20 put pot in sink
- 任务：put pot in sink
- 规则：放置任务失败原因是机器人抓取锅后未导航到水槽就直接放置，下次应先导航到sink再执行move pot to sink。


### 2026-06-30 15:18 put pot in sink
- 任务：put pot in sink
- 规则：放置任务失败原因是缺少导航到sink的步骤，下次应先导航到sink再执行放置。


### 2026-06-30 15:17 put apple in stove
- 任务：put apple in stove
- 规则：search_and_grasp失败原因是全场未发现apple，应先检查其他未搜索区域（如cabinet/drawer）再尝试抓取；放置前必须导航到stove，不能省略。


### 2026-06-26 19:20 put pot in sink
- 任务：put pot in sink
- 规则：放置任务失败原因是缺少导航到sink的步骤，下次应先导航到sink，再执行move pot to sink。


### 2026-06-26 19:17 put pot in sink
- 任务：put pot in sink
- 规则：放置到水槽失败原因是机器人未在水槽处，下次应先导航到sink再执行move pot to sink。


### 2026-06-26 17:39 put cup in stove
- 任务：put cup in stove
- 规则：放置失败原因是未持有杯子，因为抓取后未重新导航到炉灶就执行放置，下次应先导航到炉灶再执行move cup to stove。


### 2026-06-26 16:18 put mug in stove
- 任务：put mug in stove
- 规则：放置失败原因是机器人已在炉灶前但未完成放置动作，下次应先确认是否已执行“导航到stove”再执行“move mug to stove”，两步缺一不可。


### 2026-06-25 17:47 put mug in countertop
- 任务：put mug in countertop
- 规则：放置失败原因是缺少导航到countertop 1，下次应先导航到目标位置再执行move。


### 2026-06-25 17:46 clean some fork and put it in drawer.
- 任务：clean some fork and put it in drawer.
- 规则：导航到sinkbasin 1失败原因是使用了坐标，下次应先使用目标名称导航到sinkbasin 1，再执行清洁。


### 2026-06-25 16:39 put mug in stove
- 任务：put mug in stove
- 规则：搜索并抓取马克杯失败，原因是所有位置均未找到mug，下次应先检查其他未搜索区域（如countertop、table）或确认mug是否已被使用。


### 2026-06-25 16:37 put mug in sink
- 任务：put mug in sink
- 规则：搜索并抓取马克杯(mug)失败原因是所有位置都未找到该物体，下次应先检查其他房间或确认物体是否存在，避免无效搜索。


### 2026-06-25 放置失败的真正原因是缺少导航
- 任务：put X in Y
- 规则：move X to Y 返回 "Nothing happens" / 失败时，根因通常是**机器人不在 Y**（搜索阶段已移动到别处），
  而非"目标被占用"。修复办法是放置前补一个"导航到 Y"子任务，不要去检查"是否有空位"。

### 2026-06-24 put mug in shelf
- 任务：put mug in shelf
- 规则：任务失败原因是最终将 plate 放到了 shelf，但用户要求放 mug，下次应先确认当前持有物体是否为 mug，若不是则需先搜索并抓取 mug。
