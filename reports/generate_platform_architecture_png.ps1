Add-Type -AssemblyName System.Drawing

$out = Join-Path $PSScriptRoot 'platform_architecture.png'
$w = 2400; $h = 1600
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$g.Clear([System.Drawing.Color]::White)

$font = New-Object System.Drawing.Font('Microsoft YaHei', 21)
$small = New-Object System.Drawing.Font('Microsoft YaHei', 15)
$title = New-Object System.Drawing.Font('Microsoft YaHei', 32, [System.Drawing.FontStyle]::Bold)
$label = New-Object System.Drawing.Font('Microsoft YaHei', 16)
$penGray = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(217,226,236), 2)
$penArrow = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(96,125,139), 3)
$penArrow.CustomEndCap = New-Object System.Drawing.Drawing2D.AdjustableArrowCap(7,7)

function CenterText($x,$y,$ww,$hh,$s,$f,$color) {
  $size = $g.MeasureString($s,$f)
  $g.DrawString($s,$f,(New-Object System.Drawing.SolidBrush($color)),($x+($ww-$size.Width)/2),($y+($hh-$size.Height)/2))
}
function Box($x,$y,$ww,$hh,$t,$s,$fill,$stroke) {
  $r = New-Object System.Drawing.RectangleF($x,$y,$ww,$hh)
  $path = New-Object System.Drawing.Drawing2D.GraphicsPath
  $rad=24; $path.AddArc($x,$y,$rad,$rad,180,90); $path.AddArc($x+$ww-$rad,$y,$rad,$rad,270,90); $path.AddArc($x+$ww-$rad,$y+$hh-$rad,$rad,$rad,0,90); $path.AddArc($x,$y+$hh-$rad,$rad,$rad,90,90); $path.CloseFigure()
  $g.FillPath((New-Object System.Drawing.SolidBrush($fill)),$path); $g.DrawPath((New-Object System.Drawing.Pen($stroke,3)),$path)
  CenterText $x ($y+10) $ww 38 $t $font ([System.Drawing.Color]::FromArgb(24,59,86))
  CenterText $x ($y+50) $ww ($hh-50) $s $small ([System.Drawing.Color]::FromArgb(66,84,102))
}
function Arrow($x1,$y1,$x2,$y2) { $g.DrawLine($penArrow,$x1,$y1,$x2,$y2) }

CenterText 0 30 $w 65 '算电协同平台总体架构' $title ([System.Drawing.Color]::FromArgb(24,59,86))
CenterText 0 95 $w 35 '基础时序数据驱动的任务调度—电网仿真—协同优化闭环' $label ([System.Drawing.Color]::FromArgb(96,125,139))

foreach($item in @(@(150,'数据输入层'),@(455,'仿真与调度层'),@(780,'优化决策层'),@(1105,'电网计算层'),@(1410,'输出与分析层'))) {
  $g.DrawLine($penGray,90,$item[0]-22,$w-70,$item[0]-22)
  CenterText 0 ($item[0]+8) 130 25 $item[1] $label ([System.Drawing.Color]::FromArgb(96,125,139))
}

$blue=[System.Drawing.Color]::FromArgb(238,245,250); $teal=[System.Drawing.Color]::FromArgb(234,244,244); $orange=[System.Drawing.Color]::FromArgb(255,246,229); $purple=[System.Drawing.Color]::FromArgb(241,240,250); $gray=[System.Drawing.Color]::FromArgb(247,247,247)
Box 130 165 390 120 '平台配置' 'platform.yaml' $blue ([System.Drawing.Color]::FromArgb(40,75,99))
Box 580 165 390 120 '任务数据表' '提交时间、时长、算力需求' $blue ([System.Drawing.Color]::FromArgb(40,75,99))
Box 1030 165 390 120 '电网时序' '负荷 / 光伏 / 风电' $blue ([System.Drawing.Color]::FromArgb(40,75,99))
Box 1480 165 390 120 '基础发电表' 'base_generation_pu_second.csv' $blue ([System.Drawing.Color]::FromArgb(40,75,99))
Box 1930 165 350 120 '设备功率曲线' 'GPU、制冷、UPS、网络' $blue ([System.Drawing.Color]::FromArgb(40,75,99))

Box 220 480 560 125 '仿真时钟与数据加载' '秒级推进；现实时间映射；时序读取' $teal ([System.Drawing.Color]::FromArgb(42,111,115))
Box 920 480 560 125 '任务生命周期管理' '提交 → 调度 → 开始 → 结束' $teal ([System.Drawing.Color]::FromArgb(42,111,115))
Box 1620 480 560 125 '数据中心设备仿真' '算力、制冷、UPS、网络、PUE' $teal ([System.Drawing.Color]::FromArgb(42,111,115))

Box 220 805 560 125 '模式一：非协同优化' '固定峰谷电价 + 规则调度' $orange ([System.Drawing.Color]::FromArgb(201,133,26))
Box 920 805 560 125 '模式二：分层优化' '先分配数据中心，再优化能源' $orange ([System.Drawing.Color]::FromArgb(201,133,26))
Box 1620 805 560 125 '模式三：联合优化' '任务分配与能源调度一体化' $orange ([System.Drawing.Color]::FromArgb(201,133,26))
CenterText 0 945 $w 35 '目标函数接口：成本、碳排放、延迟或用户自定义目标' $label ([System.Drawing.Color]::FromArgb(138,90,0))

Box 150 1140 450 125 '节点负荷构造' '基础负荷 + 任务增量负荷' $purple ([System.Drawing.Color]::FromArgb(94,84,142))
Box 680 1140 450 125 '发电构造' '基础发电 + 新能源 + 增量发电' $purple ([System.Drawing.Color]::FromArgb(94,84,142))
Box 1210 1140 450 125 '电网模型' 'Pandapower IEEE 39 节点' $purple ([System.Drawing.Color]::FromArgb(94,84,142))
Box 1740 1140 450 125 '潮流与评价' '电价、碳排放、约束' $purple ([System.Drawing.Color]::FromArgb(94,84,142))

Box 220 1435 450 90 '任务结果' 'task_execution.csv' $gray ([System.Drawing.Color]::FromArgb(96,125,139))
Box 730 1435 450 90 '电网结果' 'simulation_stats.csv' $gray ([System.Drawing.Color]::FromArgb(96,125,139))
Box 1240 1435 450 90 '可视化报告' '功率、任务、算力、时长' $gray ([System.Drawing.Color]::FromArgb(96,125,139))
Box 1750 1435 450 90 '实时日志' '状态与统计' $gray ([System.Drawing.Color]::FromArgb(96,125,139))

Arrow 325 285 430 480; Arrow 775 285 1100 480; Arrow 1225 285 1900 480; Arrow 1675 285 1900 480; Arrow 2105 285 1900 480
Arrow 780 542 920 542; Arrow 1480 542 1620 542
Arrow 500 605 500 805; Arrow 1200 605 1200 805; Arrow 1900 605 1900 805
Arrow 500 930 375 1140; Arrow 1200 930 905 1140; Arrow 1900 930 1435 1140
Arrow 600 1202 680 1202; Arrow 1130 1202 1210 1202; Arrow 1660 1202 1740 1202
Arrow 375 1265 445 1435; Arrow 905 1265 955 1435; Arrow 1435 1265 1465 1435; Arrow 1965 1265 1975 1435

$bmp.Save($out,[System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output $out
