// 动作目录用于产品设计；只保存配置，不执行系统操作。
const ACTION_CATALOG = [
  {
    "id": "shortcut",
    "group": "键鼠输入",
    "name": "发送快捷键",
    "description": "发送组合键，可控制应用中的任意快捷键操作。",
    "fields": [
      {
        "key": "value",
        "label": "快捷键",
        "initial": "Ctrl + Tab",
        "kind": "text",
        "choices": []
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      },
      {
        "key": "count",
        "label": "发送次数",
        "initial": "1",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "key",
    "group": "键鼠输入",
    "name": "按下或释放按键",
    "description": "单独控制按下、释放或一次完整按键。",
    "fields": [
      {
        "key": "value",
        "label": "按键",
        "initial": "Shift",
        "kind": "text",
        "choices": []
      },
      {
        "key": "operation",
        "label": "操作",
        "initial": "按下并释放",
        "kind": "select",
        "choices": [
          "按下并释放",
          "按下",
          "释放"
        ]
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "mouse",
    "group": "键鼠输入",
    "name": "鼠标点击或按下释放",
    "description": "模拟鼠标按钮，可选择单击、双击或按下释放。",
    "fields": [
      {
        "key": "value",
        "label": "按钮",
        "initial": "左键",
        "kind": "select",
        "choices": [
          "左键",
          "右键",
          "中键",
          "侧键 1",
          "侧键 2"
        ]
      },
      {
        "key": "operation",
        "label": "操作",
        "initial": "单击",
        "kind": "select",
        "choices": [
          "单击",
          "双击",
          "按下",
          "释放"
        ]
      },
      {
        "key": "position",
        "label": "位置",
        "initial": "当前位置",
        "kind": "select",
        "choices": [
          "当前位置",
          "手势起点",
          "指定坐标"
        ]
      },
      {
        "key": "x",
        "label": "X 坐标",
        "initial": "0",
        "kind": "text",
        "choices": []
      },
      {
        "key": "y",
        "label": "Y 坐标",
        "initial": "0",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "模拟输入的授权与 GNOME 接入需要验证；不会新增无轨迹手势触发。",
    "children": false
  },
  {
    "id": "pointer",
    "group": "键鼠输入",
    "name": "移动鼠标指针",
    "description": "移动到绝对、相对或窗口内部坐标。",
    "fields": [
      {
        "key": "value",
        "label": "坐标参考",
        "initial": "目标窗口内",
        "kind": "select",
        "choices": [
          "屏幕绝对坐标",
          "相对当前位置",
          "目标窗口内"
        ]
      },
      {
        "key": "x",
        "label": "X",
        "initial": "100",
        "kind": "text",
        "choices": []
      },
      {
        "key": "y",
        "label": "Y",
        "initial": "100",
        "kind": "text",
        "choices": []
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "scroll",
    "group": "键鼠输入",
    "name": "滚动",
    "description": "指定方向与滚动量，支持水平滚动。",
    "fields": [
      {
        "key": "value",
        "label": "方向",
        "initial": "向下",
        "kind": "select",
        "choices": [
          "向上",
          "向下",
          "向左",
          "向右"
        ]
      },
      {
        "key": "amount",
        "label": "滚动量",
        "initial": "3",
        "kind": "text",
        "choices": []
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      }
    ],
    "note": "指针不在目标窗口内时，先移到目标窗口中心再滚动，避免滚动另一窗口。",
    "children": false
  },
  {
    "id": "drag",
    "group": "键鼠输入",
    "name": "拖动",
    "description": "通过起终坐标与按钮配置拖动，不编写脚本。",
    "fields": [
      {
        "key": "value",
        "label": "按钮",
        "initial": "左键",
        "kind": "select",
        "choices": [
          "左键",
          "右键",
          "中键"
        ]
      },
      {
        "key": "start",
        "label": "起点坐标",
        "initial": "100, 100",
        "kind": "text",
        "choices": []
      },
      {
        "key": "end",
        "label": "终点坐标",
        "initial": "300, 200",
        "kind": "text",
        "choices": []
      },
      {
        "key": "duration",
        "label": "持续时间（毫秒）",
        "initial": "300",
        "kind": "text",
        "choices": []
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "text",
    "group": "文本与剪贴板",
    "name": "输入文本",
    "description": "输入多行文本，支持插入变量。",
    "fields": [
      {
        "key": "value",
        "label": "文本内容",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      },
      {
        "key": "method",
        "label": "输入方式",
        "initial": "自动",
        "kind": "select",
        "choices": [
          "自动",
          "模拟文本输入",
          "临时剪贴板粘贴"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "paste",
    "group": "文本与剪贴板",
    "name": "粘贴文本",
    "description": "将指定文本粘贴到目标窗口，可恢复原剪贴板。",
    "fields": [
      {
        "key": "value",
        "label": "文本内容",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      },
      {
        "key": "restore",
        "label": "粘贴后剪贴板",
        "initial": "恢复原内容",
        "kind": "select",
        "choices": [
          "恢复原内容",
          "保留本次内容"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "clipboard.read",
    "group": "文本与剪贴板",
    "name": "读取剪贴板",
    "description": "读取当前纯文本供后续步骤使用。",
    "fields": [
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "剪贴板接入与恢复原内容的可靠性需要验证。",
    "children": false
  },
  {
    "id": "clipboard.write",
    "group": "文本与剪贴板",
    "name": "写入剪贴板",
    "description": "设置纯文本剪贴板。",
    "fields": [
      {
        "key": "value",
        "label": "文本内容",
        "initial": "",
        "kind": "textarea",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "clipboard.clear",
    "group": "文本与剪贴板",
    "name": "清空剪贴板",
    "description": "清除当前剪贴板内容。",
    "fields": [],
    "note": "",
    "children": false
  },
  {
    "id": "selection.copy",
    "group": "文本与剪贴板",
    "name": "获取选中文本",
    "description": "向目标窗口发送复制操作，读取复制结果。",
    "fields": [
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      },
      {
        "key": "timeout",
        "label": "等待超时（毫秒）",
        "initial": "1000",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "应用需支持复制；未能获取时报告失败，不使用旧剪贴板伪装结果。",
    "children": false
  },
  {
    "id": "launch",
    "group": "应用与命令",
    "name": "打开程序",
    "description": "通过应用条目启动，并可接收新窗口作为后续目标。",
    "fields": [
      {
        "key": "value",
        "label": "应用 ID",
        "initial": "org.gnome.Nautilus",
        "kind": "text",
        "choices": []
      },
      {
        "key": "arguments",
        "label": "启动参数",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "windowTarget",
        "label": "新窗口作为动作目标",
        "initial": "否",
        "kind": "select",
        "choices": [
          "否",
          "是"
        ]
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "app.activate",
    "group": "应用与命令",
    "name": "激活或打开应用",
    "description": "已有匹配窗口则激活，否则启动应用。",
    "fields": [
      {
        "key": "value",
        "label": "应用 ID",
        "initial": "org.gnome.Nautilus",
        "kind": "text",
        "choices": []
      },
      {
        "key": "title",
        "label": "窗口标题包含",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "timeout",
        "label": "等待超时（毫秒）",
        "initial": "5000",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "command",
    "group": "应用与命令",
    "name": "运行命令",
    "description": "配置命令、目录与环境，获取退出状态和输出。",
    "fields": [
      {
        "key": "value",
        "label": "命令",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "mode",
        "label": "运行方式",
        "initial": "直接启动程序",
        "kind": "select",
        "choices": [
          "直接启动程序",
          "通过 Shell 运行"
        ]
      },
      {
        "key": "arguments",
        "label": "参数（直接启动时）",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "directory",
        "label": "工作目录",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "environment",
        "label": "环境变量（名称=值，每行一项）",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "waitExit",
        "label": "等待结束",
        "initial": "是",
        "kind": "select",
        "choices": [
          "是",
          "否"
        ]
      },
      {
        "key": "timeout",
        "label": "超时（毫秒，0 表示不设超时）",
        "initial": "10000",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "uri.open",
    "group": "应用与命令",
    "name": "打开链接或文件",
    "description": "使用默认程序打开网址、路径或 URI。",
    "fields": [
      {
        "key": "value",
        "label": "网址或文件路径",
        "initial": "https://example.com",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "app.quit",
    "group": "应用与命令",
    "name": "关闭应用窗口",
    "description": "正常请求关闭匹配窗口，可指定当前或全部匹配窗口。",
    "fields": [
      {
        "key": "value",
        "label": "应用 ID",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "mode",
        "label": "关闭范围",
        "initial": "当前目标窗口",
        "kind": "select",
        "choices": [
          "当前目标窗口",
          "该应用的所有窗口"
        ]
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "process.signal",
    "group": "应用与命令",
    "name": "向进程发送信号",
    "description": "高级动作，通过进程 ID 请求结束或暂停进程。",
    "fields": [
      {
        "key": "value",
        "label": "进程 ID",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "signal",
        "label": "信号",
        "initial": "TERM",
        "kind": "select",
        "choices": [
          "TERM",
          "INT",
          "STOP",
          "CONT"
        ]
      }
    ],
    "note": "进程权限受系统限制。",
    "children": false
  },
  {
    "id": "window",
    "group": "窗口与工作区",
    "name": "窗口操作",
    "description": "最大化、还原、布局、置顶及关闭目标窗口。",
    "fields": [
      {
        "key": "value",
        "label": "操作",
        "initial": "切换最大化",
        "kind": "select",
        "choices": [
          "激活",
          "最大化",
          "还原",
          "切换最大化",
          "最小化",
          "取消最小化",
          "关闭窗口",
          "左半屏",
          "右半屏",
          "进入全屏",
          "退出全屏",
          "切换全屏",
          "置顶",
          "取消置顶",
          "置顶 / 取消置顶",
          "所有工作区可见",
          "仅当前工作区可见",
          "移至上一工作区",
          "移至下一工作区"
        ]
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "window.find",
    "group": "窗口与工作区",
    "name": "查找窗口",
    "description": "按应用与标题查找窗口，结果可作为后续目标。",
    "fields": [
      {
        "key": "value",
        "label": "应用 ID",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "title",
        "label": "标题包含",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "workspace",
        "label": "工作区范围",
        "initial": "当前工作区",
        "kind": "select",
        "choices": [
          "当前工作区",
          "所有工作区"
        ]
      },
      {
        "key": "pick",
        "label": "多个结果时",
        "initial": "最近使用",
        "kind": "select",
        "choices": [
          "最近使用",
          "最前方"
        ]
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "window.target",
    "group": "窗口与工作区",
    "name": "设置动作目标窗口",
    "description": "明确指定后续快捷键与窗口动作的目标。",
    "fields": [
      {
        "key": "value",
        "label": "目标来源",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前聚焦窗口",
          "窗口变量"
        ]
      },
      {
        "key": "variable",
        "label": "窗口变量名称",
        "initial": "窗口",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "window.info",
    "group": "窗口与工作区",
    "name": "读取窗口信息",
    "description": "读取标题、应用、位置、尺寸、工作区或状态。",
    "fields": [
      {
        "key": "value",
        "label": "信息",
        "initial": "标题",
        "kind": "select",
        "choices": [
          "标题",
          "应用 ID",
          "位置与尺寸",
          "工作区",
          "所在显示器",
          "是否最大化",
          "是否全屏",
          "是否置顶"
        ]
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "window.geometry",
    "group": "窗口与工作区",
    "name": "移动或调整窗口尺寸",
    "description": "按像素或工作区比例设定位置和尺寸。",
    "fields": [
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      },
      {
        "key": "unit",
        "label": "单位",
        "initial": "像素",
        "kind": "select",
        "choices": [
          "像素",
          "工作区百分比"
        ]
      },
      {
        "key": "x",
        "label": "X",
        "initial": "0",
        "kind": "text",
        "choices": []
      },
      {
        "key": "y",
        "label": "Y",
        "initial": "0",
        "kind": "text",
        "choices": []
      },
      {
        "key": "width",
        "label": "宽度",
        "initial": "960",
        "kind": "text",
        "choices": []
      },
      {
        "key": "height",
        "label": "高度",
        "initial": "700",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "window.monitor",
    "group": "窗口与工作区",
    "name": "移动窗口到显示器",
    "description": "移动到指定、上一个或下一个显示器。",
    "fields": [
      {
        "key": "value",
        "label": "显示器",
        "initial": "下一个显示器",
        "kind": "select",
        "choices": [
          "下一个显示器",
          "上一个显示器",
          "主显示器",
          "指定编号"
        ]
      },
      {
        "key": "index",
        "label": "显示器编号",
        "initial": "1",
        "kind": "text",
        "choices": []
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "workspace.switch",
    "group": "窗口与工作区",
    "name": "切换工作区",
    "description": "选择编号、上一或下一工作区。",
    "fields": [
      {
        "key": "value",
        "label": "目标",
        "initial": "下一工作区",
        "kind": "select",
        "choices": [
          "上一工作区",
          "下一工作区",
          "指定编号"
        ]
      },
      {
        "key": "index",
        "label": "工作区编号",
        "initial": "1",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "workspace.move",
    "group": "窗口与工作区",
    "name": "移动窗口到工作区",
    "description": "将目标窗口移到指定工作区，可同时切换过去。",
    "fields": [
      {
        "key": "value",
        "label": "工作区编号",
        "initial": "2",
        "kind": "text",
        "choices": []
      },
      {
        "key": "target",
        "label": "目标窗口",
        "initial": "起点窗口",
        "kind": "select",
        "choices": [
          "起点窗口",
          "当前动作目标",
          "查找到的窗口"
        ]
      },
      {
        "key": "follow",
        "label": "同时切换工作区",
        "initial": "否",
        "kind": "select",
        "choices": [
          "否",
          "是"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "desktop.overview",
    "group": "窗口与工作区",
    "name": "概览或应用列表",
    "description": "显示 GNOME 概览或应用列表。",
    "fields": [
      {
        "key": "value",
        "label": "操作",
        "initial": "切换概览",
        "kind": "select",
        "choices": [
          "显示概览",
          "隐藏概览",
          "切换概览",
          "显示应用列表"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "desktop.show",
    "group": "窗口与工作区",
    "name": "显示桌面或恢复窗口",
    "description": "收起当前工作区窗口，再次执行恢复原状态。",
    "fields": [
      {
        "key": "value",
        "label": "操作",
        "initial": "切换",
        "kind": "select",
        "choices": [
          "显示桌面",
          "恢复窗口",
          "切换"
        ]
      }
    ],
    "note": "需要验证窗口状态的保存与恢复。",
    "children": false
  },
  {
    "id": "wait",
    "group": "流程控制",
    "name": "等待时长",
    "description": "暂停指定毫秒数，支持数字变量。",
    "fields": [
      {
        "key": "value",
        "label": "等待时长（毫秒）",
        "initial": "150",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "wait.condition",
    "group": "流程控制",
    "name": "等待条件成立",
    "description": "等待窗口、文件、变量或剪贴板满足条件。",
    "fields": [
      {
        "key": "value",
        "label": "条件类型",
        "initial": "窗口出现",
        "kind": "select",
        "choices": [
          "窗口出现",
          "窗口消失",
          "窗口标题包含",
          "文件存在",
          "变量等于",
          "剪贴板包含"
        ]
      },
      {
        "key": "subject",
        "label": "条件对象（应用、路径或变量）",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "compare",
        "label": "比较值",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "timeout",
        "label": "超时（毫秒）",
        "initial": "5000",
        "kind": "text",
        "choices": []
      },
      {
        "key": "interval",
        "label": "检查间隔（毫秒）",
        "initial": "100",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "condition",
    "group": "流程控制",
    "name": "条件分支",
    "description": "按上下文或变量比较结果进入成立或否则分支。",
    "fields": [
      {
        "key": "value",
        "label": "比较对象",
        "initial": "应用名称",
        "kind": "select",
        "choices": [
          "应用名称",
          "窗口标题",
          "变量",
          "剪贴板",
          "文件是否存在",
          "命令退出码"
        ]
      },
      {
        "key": "source",
        "label": "变量名称或文件路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "operator",
        "label": "比较方式",
        "initial": "等于",
        "kind": "select",
        "choices": [
          "等于",
          "不等于",
          "包含",
          "不包含",
          "大于",
          "小于",
          "为空",
          "不为空",
          "为真",
          "为假"
        ]
      },
      {
        "key": "compare",
        "label": "比较值",
        "initial": "Firefox",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": true
  },
  {
    "id": "repeat",
    "group": "流程控制",
    "name": "有限次数重复",
    "description": "按指定次数或数字变量重复子步骤。",
    "fields": [
      {
        "key": "value",
        "label": "重复次数",
        "initial": "3",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": true
  },
  {
    "id": "foreach",
    "group": "流程控制",
    "name": "遍历列表",
    "description": "对列表中每项执行子步骤。",
    "fields": [
      {
        "key": "value",
        "label": "列表变量",
        "initial": "文件列表",
        "kind": "text",
        "choices": []
      },
      {
        "key": "item",
        "label": "当前项变量名",
        "initial": "当前项",
        "kind": "text",
        "choices": []
      },
      {
        "key": "itemKind",
        "label": "当前项类型",
        "initial": "文本",
        "kind": "select",
        "choices": [
          "自动",
          "文本",
          "数字",
          "布尔值",
          "列表",
          "窗口",
          "数据"
        ]
      },
      {
        "key": "index",
        "label": "索引变量名",
        "initial": "索引",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": true
  },
  {
    "id": "loop.break",
    "group": "流程控制",
    "name": "退出当前重复",
    "description": "结束最近一层重复或列表遍历。",
    "fields": [],
    "note": "仅可放在重复或遍历内部。",
    "children": false
  },
  {
    "id": "loop.continue",
    "group": "流程控制",
    "name": "跳过当前循环项",
    "description": "跳过本轮剩余动作并进入下一轮。",
    "fields": [],
    "note": "仅可放在重复或遍历内部。",
    "children": false
  },
  {
    "id": "flow.stop",
    "group": "流程控制",
    "name": "停止动作序列",
    "description": "主动结束本次执行，可显示说明。",
    "fields": [
      {
        "key": "value",
        "label": "停止原因",
        "initial": "",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "flow.call",
    "group": "流程控制",
    "name": "调用可复用动作",
    "description": "引用独立保存的动作序列并传递参数。",
    "fields": [
      {
        "key": "value",
        "label": "动作序列名称",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "arguments",
        "label": "输入参数（名称=值）",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "引用会同步更新；禁止直接或间接递归。",
    "children": false
  },
  {
    "id": "variable",
    "group": "变量与数据",
    "name": "设置变量",
    "description": "设置文本、数字、布尔值或列表。",
    "fields": [
      {
        "key": "name",
        "label": "变量名称",
        "initial": "次数",
        "kind": "text",
        "choices": []
      },
      {
        "key": "kind",
        "label": "类型",
        "initial": "数字",
        "kind": "select",
        "choices": [
          "文本",
          "数字",
          "布尔值",
          "列表"
        ]
      },
      {
        "key": "value",
        "label": "变量值",
        "initial": "3",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "variable.read",
    "group": "变量与数据",
    "name": "读取上下文值",
    "description": "读取起点窗口、鼠标、剪贴板或时间等上下文。",
    "fields": [
      {
        "key": "value",
        "label": "来源",
        "initial": "起点窗口标题",
        "kind": "select",
        "choices": [
          "起点应用 ID",
          "起点窗口标题",
          "起点坐标",
          "当前指针坐标",
          "当前工作区",
          "当前显示器",
          "剪贴板文本",
          "当前日期时间",
          "用户主目录"
        ]
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "number.calculate",
    "group": "变量与数据",
    "name": "数字计算",
    "description": "通过操作符进行计算，不输入代码。",
    "fields": [
      {
        "key": "left",
        "label": "左值",
        "initial": "0",
        "kind": "text",
        "choices": []
      },
      {
        "key": "value",
        "label": "运算",
        "initial": "加",
        "kind": "select",
        "choices": [
          "加",
          "减",
          "乘",
          "除",
          "取余",
          "最小值",
          "最大值",
          "四舍五入"
        ]
      },
      {
        "key": "right",
        "label": "右值",
        "initial": "1",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "text.transform",
    "group": "变量与数据",
    "name": "处理文本",
    "description": "替换、截取、连接、大小写转换和去空白。",
    "fields": [
      {
        "key": "value",
        "label": "文本",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "operation",
        "label": "操作",
        "initial": "去首尾空白",
        "kind": "select",
        "choices": [
          "去首尾空白",
          "转大写",
          "转小写",
          "替换",
          "截取",
          "连接",
          "获取长度",
          "按分隔符拆分",
          "按分隔符合并"
        ]
      },
      {
        "key": "argument",
        "label": "参数（查找文本、位置或分隔符）",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "replacement",
        "label": "替换内容或附加文本",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "date.format",
    "group": "变量与数据",
    "name": "格式化日期时间",
    "description": "生成指定格式的日期或时间文本。",
    "fields": [
      {
        "key": "value",
        "label": "格式",
        "initial": "YYYY-MM-DD",
        "kind": "text",
        "choices": []
      },
      {
        "key": "timezone",
        "label": "时区",
        "initial": "本地时区",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "number.random",
    "group": "变量与数据",
    "name": "生成随机数",
    "description": "生成指定范围内的整数。",
    "fields": [
      {
        "key": "min",
        "label": "最小值",
        "initial": "1",
        "kind": "text",
        "choices": []
      },
      {
        "key": "max",
        "label": "最大值",
        "initial": "100",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "json.parse",
    "group": "变量与数据",
    "name": "解析 JSON",
    "description": "把文本转换为结构化数据，供后续读取字段。",
    "fields": [
      {
        "key": "value",
        "label": "JSON 文本",
        "initial": "{}",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "data.field",
    "group": "变量与数据",
    "name": "读取数据字段",
    "description": "按字段路径读取命令、HTTP、窗口或 JSON 结果。",
    "fields": [
      {
        "key": "value",
        "label": "对象变量",
        "initial": "结果",
        "kind": "text",
        "choices": []
      },
      {
        "key": "path",
        "label": "字段路径",
        "initial": "stdout",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "list.change",
    "group": "变量与数据",
    "name": "操作列表",
    "description": "追加、移除、读取项、查找或获取列表长度。",
    "fields": [
      {
        "key": "value",
        "label": "列表变量",
        "initial": "文件列表",
        "kind": "text",
        "choices": []
      },
      {
        "key": "operation",
        "label": "操作",
        "initial": "追加",
        "kind": "select",
        "choices": [
          "追加",
          "移除指定索引",
          "读取指定索引",
          "查找",
          "获取长度"
        ]
      },
      {
        "key": "argument",
        "label": "索引或值",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "file.read",
    "group": "文件与路径",
    "name": "读取文本文件",
    "description": "读取文件内容到变量，可指定编码。",
    "fields": [
      {
        "key": "value",
        "label": "文件路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "encoding",
        "label": "编码",
        "initial": "UTF-8",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "file.write",
    "group": "文件与路径",
    "name": "写入或追加文本文件",
    "description": "将文本或变量写入指定文件。",
    "fields": [
      {
        "key": "value",
        "label": "文件路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "content",
        "label": "文本内容",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "mode",
        "label": "写入方式",
        "initial": "覆盖",
        "kind": "select",
        "choices": [
          "覆盖",
          "追加"
        ]
      },
      {
        "key": "encoding",
        "label": "编码",
        "initial": "UTF-8",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "file.copy",
    "group": "文件与路径",
    "name": "复制文件或目录",
    "description": "复制到目标路径，指定冲突处理方式。",
    "fields": [
      {
        "key": "value",
        "label": "源路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "destination",
        "label": "目标路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "conflict",
        "label": "同名处理",
        "initial": "报告失败",
        "kind": "select",
        "choices": [
          "报告失败",
          "覆盖",
          "自动重命名"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "file.move",
    "group": "文件与路径",
    "name": "移动或重命名",
    "description": "移动文件、目录或修改名称。",
    "fields": [
      {
        "key": "value",
        "label": "源路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "destination",
        "label": "目标路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "conflict",
        "label": "同名处理",
        "initial": "报告失败",
        "kind": "select",
        "choices": [
          "报告失败",
          "覆盖",
          "自动重命名"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "file.trash",
    "group": "文件与路径",
    "name": "移到回收站",
    "description": "移入回收站；无法回收时报告失败。",
    "fields": [
      {
        "key": "value",
        "label": "路径",
        "initial": "",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "directory.create",
    "group": "文件与路径",
    "name": "创建目录",
    "description": "创建目录，可按需创建父目录。",
    "fields": [
      {
        "key": "value",
        "label": "目录路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "parents",
        "label": "创建父目录",
        "initial": "是",
        "kind": "select",
        "choices": [
          "是",
          "否"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "directory.list",
    "group": "文件与路径",
    "name": "列出目录内容",
    "description": "取得文件列表，配合遍历操作。",
    "fields": [
      {
        "key": "value",
        "label": "目录路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "filter",
        "label": "文件名筛选",
        "initial": "*",
        "kind": "text",
        "choices": []
      },
      {
        "key": "recursive",
        "label": "包含子目录",
        "initial": "否",
        "kind": "select",
        "choices": [
          "否",
          "是"
        ]
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "file.info",
    "group": "文件与路径",
    "name": "读取路径信息",
    "description": "查询是否存在、文件名、扩展名、大小或修改时间。",
    "fields": [
      {
        "key": "value",
        "label": "路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "property",
        "label": "信息",
        "initial": "是否存在",
        "kind": "select",
        "choices": [
          "是否存在",
          "是否为目录",
          "文件名",
          "扩展名",
          "父目录",
          "大小",
          "修改时间"
        ]
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "volume",
    "group": "系统与媒体",
    "name": "调节音量或静音",
    "description": "调整输出或输入设备的音量和静音状态。",
    "fields": [
      {
        "key": "value",
        "label": "操作",
        "initial": "增加音量",
        "kind": "select",
        "choices": [
          "增加音量",
          "降低音量",
          "设置音量",
          "切换静音",
          "静音",
          "取消静音"
        ]
      },
      {
        "key": "amount",
        "label": "百分比",
        "initial": "5",
        "kind": "text",
        "choices": []
      },
      {
        "key": "device",
        "label": "设备",
        "initial": "默认输出",
        "kind": "select",
        "choices": [
          "默认输出",
          "默认输入"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "brightness",
    "group": "系统与媒体",
    "name": "调节亮度",
    "description": "调节系统支持的显示器亮度。",
    "fields": [
      {
        "key": "value",
        "label": "操作",
        "initial": "增加",
        "kind": "select",
        "choices": [
          "增加",
          "降低",
          "设置"
        ]
      },
      {
        "key": "amount",
        "label": "百分比",
        "initial": "10",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "依赖硬件与 GNOME 亮度控制能力；不能假设外接显示器支持。",
    "children": false
  },
  {
    "id": "media",
    "group": "系统与媒体",
    "name": "控制媒体播放",
    "description": "通过 MPRIS 控制播放器。",
    "fields": [
      {
        "key": "value",
        "label": "操作",
        "initial": "播放 / 暂停",
        "kind": "select",
        "choices": [
          "播放",
          "暂停",
          "播放 / 暂停",
          "停止",
          "上一首",
          "下一首",
          "快进",
          "快退"
        ]
      },
      {
        "key": "player",
        "label": "播放器",
        "initial": "当前活动播放器",
        "kind": "text",
        "choices": []
      },
      {
        "key": "seconds",
        "label": "快进或快退秒数",
        "initial": "10",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "播放器必须支持对应的 MPRIS 能力。",
    "children": false
  },
  {
    "id": "notification",
    "group": "系统与媒体",
    "name": "显示通知",
    "description": "显示标题与正文，正文可引用变量。",
    "fields": [
      {
        "key": "value",
        "label": "标题",
        "initial": "WayStroke",
        "kind": "text",
        "choices": []
      },
      {
        "key": "body",
        "label": "正文",
        "initial": "",
        "kind": "textarea",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "dialog.message",
    "group": "系统与媒体",
    "name": "显示消息或询问",
    "description": "用对话框展示结果或获取确认。",
    "fields": [
      {
        "key": "value",
        "label": "标题",
        "initial": "确认操作",
        "kind": "text",
        "choices": []
      },
      {
        "key": "body",
        "label": "内容",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "buttons",
        "label": "按钮",
        "initial": "确定 / 取消",
        "kind": "select",
        "choices": [
          "确定",
          "确定 / 取消",
          "是 / 否"
        ]
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "dialog.input",
    "group": "系统与媒体",
    "name": "请求用户输入",
    "description": "执行过程中通过输入框获取文本。",
    "fields": [
      {
        "key": "value",
        "label": "提示",
        "initial": "请输入内容",
        "kind": "text",
        "choices": []
      },
      {
        "key": "default",
        "label": "默认值",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "screenshot",
    "group": "系统与媒体",
    "name": "截图",
    "description": "截图全屏、目标窗口或交互选区，可保存或复制。",
    "fields": [
      {
        "key": "value",
        "label": "范围",
        "initial": "选区",
        "kind": "select",
        "choices": [
          "选区",
          "目标窗口",
          "全屏"
        ]
      },
      {
        "key": "destination",
        "label": "输出",
        "initial": "剪贴板",
        "kind": "select",
        "choices": [
          "剪贴板",
          "文件"
        ]
      },
      {
        "key": "path",
        "label": "文件路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "截图接入与授权、窗口截图方式需要验证。",
    "children": false
  },
  {
    "id": "session",
    "group": "系统与媒体",
    "name": "锁屏或会话操作",
    "description": "锁屏、挂起或注销，可选择执行前确认。",
    "fields": [
      {
        "key": "value",
        "label": "操作",
        "initial": "锁屏",
        "kind": "select",
        "choices": [
          "锁屏",
          "挂起",
          "注销"
        ]
      },
      {
        "key": "confirm",
        "label": "执行前确认",
        "initial": "是",
        "kind": "select",
        "choices": [
          "是",
          "否"
        ]
      }
    ],
    "note": "依赖会话权限与 GNOME 接入。",
    "children": false
  },
  {
    "id": "settings.open",
    "group": "系统与媒体",
    "name": "打开系统设置",
    "description": "进入 GNOME 设置指定页面。",
    "fields": [
      {
        "key": "value",
        "label": "页面",
        "initial": "显示器",
        "kind": "select",
        "choices": [
          "显示器",
          "声音",
          "键盘",
          "鼠标与触摸板",
          "网络",
          "蓝牙",
          "电源",
          "外观"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "http.request",
    "group": "高级集成",
    "name": "发送 HTTP 请求",
    "description": "通过表单配置方法、URL、请求头和正文。",
    "fields": [
      {
        "key": "value",
        "label": "URL",
        "initial": "https://example.com",
        "kind": "text",
        "choices": []
      },
      {
        "key": "method",
        "label": "方法",
        "initial": "GET",
        "kind": "select",
        "choices": [
          "GET",
          "POST",
          "PUT",
          "PATCH",
          "DELETE",
          "HEAD"
        ]
      },
      {
        "key": "headers",
        "label": "请求头（名称=值，每行一项）",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "body",
        "label": "请求正文",
        "initial": "",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "timeout",
        "label": "超时（毫秒）",
        "initial": "10000",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "dbus.call",
    "group": "高级集成",
    "name": "调用 D-Bus 方法",
    "description": "连接本机服务，配置总线、方法与类型化参数。",
    "fields": [
      {
        "key": "bus",
        "label": "总线",
        "initial": "会话总线",
        "kind": "select",
        "choices": [
          "会话总线",
          "系统总线"
        ]
      },
      {
        "key": "service",
        "label": "服务名",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "path",
        "label": "对象路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "interface",
        "label": "接口",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "value",
        "label": "方法名",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "signature",
        "label": "参数类型签名",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "arguments",
        "label": "参数值（设计稿暂以 JSON 列表填写）",
        "initial": "[]",
        "kind": "textarea",
        "choices": []
      },
      {
        "key": "timeout",
        "label": "超时（毫秒）",
        "initial": "5000",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "受目标服务与系统权限限制；最终界面应提供类型化参数表，不要求写代码。",
    "children": false
  },
  {
    "id": "dbus.property",
    "group": "高级集成",
    "name": "读取或设置 D-Bus 属性",
    "description": "通过表单读取或更新服务属性。",
    "fields": [
      {
        "key": "bus",
        "label": "总线",
        "initial": "会话总线",
        "kind": "select",
        "choices": [
          "会话总线",
          "系统总线"
        ]
      },
      {
        "key": "service",
        "label": "服务名",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "path",
        "label": "对象路径",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "interface",
        "label": "接口",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "value",
        "label": "属性名",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "operation",
        "label": "操作",
        "initial": "读取",
        "kind": "select",
        "choices": [
          "读取",
          "设置"
        ]
      },
      {
        "key": "content",
        "label": "设置值",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "signature",
        "label": "值类型",
        "initial": "s",
        "kind": "text",
        "choices": []
      },
      {
        "key": "output",
        "label": "结果保存到变量（可选）",
        "initial": "结果",
        "kind": "text",
        "choices": []
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "waystroke.toggle",
    "group": "WayStroke 控制",
    "name": "控制手势或文本替换",
    "description": "启用、暂停或切换功能状态。",
    "fields": [
      {
        "key": "value",
        "label": "功能",
        "initial": "手势",
        "kind": "select",
        "choices": [
          "手势",
          "文本替换"
        ]
      },
      {
        "key": "operation",
        "label": "操作",
        "initial": "切换",
        "kind": "select",
        "choices": [
          "启用",
          "暂停",
          "切换"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "waystroke.rule",
    "group": "WayStroke 控制",
    "name": "启停指定规则",
    "description": "临时启用、停用或切换规则。",
    "fields": [
      {
        "key": "value",
        "label": "规则名称",
        "initial": "",
        "kind": "text",
        "choices": []
      },
      {
        "key": "operation",
        "label": "操作",
        "initial": "切换",
        "kind": "select",
        "choices": [
          "启用",
          "停用",
          "切换"
        ]
      }
    ],
    "note": "",
    "children": false
  },
  {
    "id": "waystroke.open",
    "group": "WayStroke 控制",
    "name": "打开 WayStroke 页面",
    "description": "进入规则、文本替换、测试或设置。",
    "fields": [
      {
        "key": "value",
        "label": "页面",
        "initial": "手势规则",
        "kind": "select",
        "choices": [
          "手势规则",
          "文本替换",
          "手势测试",
          "设置"
        ]
      }
    ],
    "note": "",
    "children": false
  }
];
