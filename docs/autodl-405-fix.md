# AutoDL H3 HTTP405修复

用户任务8使用默认/videos路径，实际工作流需/api/v1/comfyui/comfyui_workflow/minimax_h3_b99_001。已将供应商1的视频配置更新为已核对的AutoDL映射：Authorization无Bearer前缀；data.task_id；data.status；data.results.0.url；支持SUCCESS/completed；输入prompt/duration/resolution，默认736p横。原Key和用户输入未修改，旧任务快照保持原样。

明确选择重新生成时，视频API和画布任务重新取得当前供应商配置；继续查询原任务仍使用原任务配置与ID。23项专项及重试测试通过。未向供应商重新提交生成请求，真实执行仍需用户主动确认。
