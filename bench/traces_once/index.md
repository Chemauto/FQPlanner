# 轨迹索引

| # | 任务 | won | 子任务 | LLM经验 |
|---|---|---|---|---|
| 1 | ['把马克杯放到水槽里面'] | ? | 4 |  |
| 2 | ['clean some fork and put it in drawer.'] | ✅ | 6 | (multi_step.md) 当放置物体到抽屉时，必须先导航到目标抽屉，再执行移动动作；若打开抽屉 |
| 3 | ['put a cloth in drawer.'] | ✅ | 4 | (multi_step.md) 当放置物体时，若抽屉关闭，必须先成功打开抽屉再执行放置，否则放置动作 |
| 4 | ['put two spatula in drawer.'] | ✅ | 7 | (multi_step.md) 当需要将多个物品放入同一抽屉时，先全部抓取完毕再统一导航到抽屉，避免 |
| 5 | ['put a cd in safe.'] | ✅ | 4 | (multi_step.md) 放置物体时，必须先导航到目标位置再执行move，即使抓取后位置接近也 |
| 6 | ['put a hot mug in coffeemachine.'] | ✅ | 5 | (multi_step.md) 加热后的杯子应直接导航到咖啡机再放置，不能省略导航步骤。 |
| 7 | ['put a statue in sidetable.'] | ✅ | 3 | (multi_step.md) 放置物体时，必须先导航到目标位置（如sidetable 1），再执行 |
| 8 | ['clean some plate and put it in microwave.'] | ✅ | 6 | (multi_step.md) 清洗盘子后，必须先导航到微波炉再放置，不能省略导航步骤。 |
| 9 | ['put a clean soapbar in toilet.'] | ✅ | 5 | (multi_step.md) 放置肥皂到马桶时，先导航到马桶再执行move，即使已在马桶旁也需导航 |
| 10 | ['put two alarmclock in shelf.'] | ✅ | 6 | (multi_step.md) 当放置第二个闹钟时，机器人已在shelf 1处，但规则要求必须先导航 |
| 11 | ['put a cellphone in dresser.'] | ✅ | 4 | (multi_step.md) 放置物品时，若目标位置（如dresser 1）有空间，可直接执行mo |
