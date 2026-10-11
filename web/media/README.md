# Homepage replay media

The browser MP4, GIF and WebP pairs use current **headless Camofox screenshots** of
the unchanged `examples/fixtures/form.html` inside a presentation frame. The frame
replays the local synthetic browser sequence documented in
`reports/acceptance.json`: Mira → London → flexible dates → prepare draft →
independently inspect the field values and `Draft ready` text.

These are **illustrative screenshot replays**, not continuous screen recordings
or fresh Jev inference runs. The historical live Jev acceptance belongs to v0.1.0.
Generation makes zero inference calls and creates no real booking or message.
Both English and Chinese media include that scope inside every frame.

- `browser-demo.mp4` / `browser-demo.zh-CN.mp4`: 12 seconds, 1280 × 720, H.264,
  no audio, browser-friendly fast-start metadata.
- `browser-demo.gif` / `browser-demo.zh-CN.gif`: looping 12-second replay,
  960 × 540, for README embedding.
- `browser-poster.webp` / `browser-poster.zh-CN.webp`: verified final-state posters.
- `showcase.json`: asset hashes, generation scope, fixture hash and independent
  DOM verification; it is not a live model-usage report.

Reproduce from the checkout with `camofox`, `ffmpeg` and `cwebp` installed. The
script reuses the durable `general` session, binds one new task tab explicitly,
and closes only that tab:

```sh
CAMOFOX_INTERACTIVE=off .venv/bin/python scripts/generate_showcase.py
```

中文：这些素材是当前合成表单界面的截图回放，不是连续录屏，也不表示重新运行
了 Jev。历史真实推理验收来自 v0.1.0；生成过程没有模型调用、真实预订或消息发送。
最终姓名、目的地、日期开关与结果文本均由程序独立读取核对。
