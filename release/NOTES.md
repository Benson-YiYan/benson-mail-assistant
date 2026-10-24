# 邮件小秘书 · CPU 占用优化

- Mac 避免未变化状态和报告列表触发重复界面更新，复用日期格式器，减少设置解析和暂停状态写盘。
- Windows 缓存报告搜索索引，修改与删除自动失效，缓存上限 500 条、约 32 MB。

Mac avoids redundant UI updates and settings parsing. Windows reuses bounded report search indexes with file-change invalidation.

Mac evita actualizaciones de interfaz y análisis repetidos. Windows reutiliza índices de búsqueda limitados e invalida los archivos modificados.

Validation: Windows GitHub Actions 40077833825 passed. Related cache tests passed (17). Mac compilation and packaged runtime checks passed on both architectures; Intel uses Rosetta. A synthetic 200-report search benchmark on Mac reduced backend CPU time by 71.5%; this is not a measured Windows desktop CPU reduction. Short Mac idle samples showed 0.0% CPU; results vary with workload.
