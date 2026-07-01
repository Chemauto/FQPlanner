# 轨迹索引

| # | 任务 | won | 子任务 | LLM经验 |
|---|---|---|---|---|
| 1 | ['把苹果捡起来放在桌上'] | ? | 3 |  |
| 2 | ['抓取苹果'] | ? | 2 |  |
| 3 | ['place the apple on the counter'] | ? | 1 |  |
| 4 | ['把苹果放在台面上'] | ? | 4 |  |
| 5 | ['抓取苹果'] | ? | 0 |  |
| 6 | ['抓取苹果'] | ? | 0 |  |
| 7 | ['抓取苹果'] | ? | 0 |  |
| 8 | ['抓取苹果'] | ? | 0 |  |
| 9 | ['抓取苹果'] | ? | 0 |  |
| 10 | ['把mug放到水槽里'] | ? | 2 |  |
| 11 | ['把mug放到水槽当中'] | ? | 4 |  |
| 12 | ['把mug放到水槽中'] | ? | 2 |  |
| 13 | ['把苹果放在灶台上'] | ? | 2 |  |
| 14 | ['把苹果放在灶台上'] | ? | 2 |  |
| 15 | ['把苹果放到灶台上'] | ? | 4 |  |
| 16 | ['把苹果放到灶台上'] | ? | 4 |  |
| 17 | ['把锅放到灶台上'] | ? | 4 |  |
| 18 | ['把锅放到水槽里'] | ? | 4 |  |
| 19 | ['把马克杯放到水槽里'] | ? | 4 |  |
| 20 | ['把锅放到水槽里，再放到灶台上'] | ? | 5 |  |
| 21 | ['把锅放进水槽里，再放到灶台上'] | ? | 5 | (place.md) 避免在放置锅时碰到灶台开关，应选择远离开关的位置放置。 |
| 22 | ['把苹果放到水槽里'] | ? | 4 |  |
| 23 | ['把锅放到水槽里面，再把锅放到灶台上'] | ? | 4 |  |
| 24 | ['把马克杯放到水槽里面'] | ? | 4 |  |
| 25 | ['把马克杯放进水槽里'] | ? | 4 |  |
| 26 | ['把碗放进水槽里'] | ? | 4 |  |
| 27 | ['把苹果放到水槽里面'] | ? | 4 |  |
| 28 | ['把海绵放到水槽里面'] | ? | 4 |  |
| 29 | ['把锅放在灶台上'] | ? | 4 |  |
| 30 | ['把锅放在灶台上'] | ? | 4 |  |
| 31 | ['把马克杯放到灶台上'] | ? | 4 |  |
| 32 | ['clean some spatula and put it in countertop'] | ? | 0 |  |
| 33 | ['clean some spatula and put it in countertop'] | ? | 0 |  |
| 34 | ['clean some spatula and put it in countertop'] | ❌ | 9 | (multi_step.md) 在drawer 7误拿了saltshaker 2，导致手持错误物体无 |
| 35 | ['clean some spatula and put it in countertop'] | ❌ | 13 | (multi_step.md) 搜索drawer 1-10时反复到达drawer 1和10，说明导航 |
| 36 | ['j'] | ❌ | 6 | (multi_step.md) 在coffeetable 2找到tissuebox 1和2后，应先确 |
| 37 | ['j'] | ? | 0 |  |
| 38 | ['j'] | ❌ | 7 | (multi_step.md) 导航到garbagecan 1失败原因是该位置不可达，下次应先确认目 |
| 39 | ['clean some fork and put it in drawer.'] | ❌ | 2 |  |
| 40 | ['put a cloth in drawer.'] | ❌ | 10 | (multi_step.md) 在 drawer 1 放置 cloth 失败原因是 drawer 1 |
| 41 | ['put two spatula in drawer.'] | ❌ | 6 | (multi_step.md) 搜索countertop 2寻找spatula失败原因是该位置没有s |
| 42 | ['put a cd in safe.'] | ❌ | 10 | (multi_step.md) move cd 1 to safe 1失败原因是未持有cd，下次应先 |
| 43 | ['put a hot mug in coffeemachine.'] | ❌ | 10 | (multi_step.md) 加热mug 1失败原因是微波炉未开启或mug未放入，下次应先打开微波 |
| 44 | ['put a statue in sidetable.'] | ❌ | 10 | (multi_step.md) 导航到sidetable 1后未持有statue就执行放置失败，下次 |
| 45 | ['clean some plate and put it in microwave.'] | ❌ | 10 | (multi_step.md) clean plate 1失败原因是手持dishsponge 2但未 |
| 46 | ['put a clean soapbar in toilet.'] | ❌ | 10 | (multi_step.md) 在sinkbasin 1清洗soapbar失败，原因是sinkbas |
| 47 | ['put two alarmclock in shelf.'] | ✅ | 8 |  |
| 48 | ['put a cellphone in dresser.'] | ❌ | 10 | (multi_step.md) 搜索drawer 8时拿起了book 1而非cellphone，失败 |
| 49 | ['clean some fork and put it in drawer.'] | ✅ | 6 | (multi_step.md) 当打开抽屉失败时，应直接尝试将物品移入抽屉，因为移动动作可能隐含打开 |
| 50 | ['put a cloth in drawer.'] | ✅ | 4 | (multi_step.md) 当抽屉关闭时，应先执行打开抽屉动作，再放入物品，否则移动物体会失败。 |
| 51 | ['put two spatula in drawer.'] | ❌ | 5 | (multi_step.md) 搜索并抓取第二个spatula失败原因是只搜索了初始位置，未检查ca |
| 52 | ['put a cd in safe.'] | ✅ | 4 | (multi_step.md) 打开保险柜后直接放入CD即可，无需额外移动操作，避免重复动作。 |
| 53 | ['put a hot mug in coffeemachine.'] | ✅ | 5 | (multi_step.md) 加热后的杯子应直接放入咖啡机，无需额外检查咖啡机上的物品状态。 |
| 54 | ['put a statue in sidetable.'] | ✅ | 3 | (multi_step.md) 当目标位置已有其他物品时，可直接将雕像移动到该位置，无需先清空。 |
| 55 | ['clean some plate and put it in microwave.'] | ✅ | 6 | (multi_step.md) 清洗盘子后直接打开微波炉并放入，无需先关门再开门，可连续操作。 |
| 56 | ['put a clean soapbar in toilet.'] | ✅ | 5 | (multi_step.md) 当目标位置已有同类物品时，应先清空或选择其他空位放置，避免覆盖或冲突 |
| 57 | ['put two alarmclock in shelf.'] | ✅ | 6 | (multi_step.md) 当需要将多个相同物品放入同一位置时，先确认目标位置已有物品，再逐个移 |
| 58 | ['put a cellphone in dresser.'] | ✅ | 4 | (multi_step.md) 当需要将物品放入抽屉柜时，若打开抽屉无效，应直接执行“移动物品到抽屉 |
