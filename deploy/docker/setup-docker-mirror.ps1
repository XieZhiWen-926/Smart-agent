<#
================================================================
 Docker 镜像加速一键配置脚本（Windows / Docker Desktop）
================================================================
【这个脚本干什么】
把 deploy/docker/daemon.json 写入 Docker Desktop 的配置文件
（%USERPROFILE%\.docker\daemon.json），并自动重启 Docker 引擎，
让"拉镜像超时"问题从根上解决。

【为什么需要它】
Docker 默认从 Docker Hub（registry-1.docker.io）拉镜像，国内直连
经常超时或极慢。配置 registry-mirrors 后，Docker 会改从国内加速
节点拉取，速度通常从"卡死"提升到几十 MB/s。

【怎么用】
  1) 关闭所有正在跑的容器（可选，脚本会重启引擎）
  2) 右键本文件 → "使用 PowerShell 运行"
     或者在本目录打开 PowerShell 执行：
         powershell -ExecutionPolicy Bypass -File .\setup-docker-mirror.ps1
  3) 脚本跑完会打印验证命令，照抄执行即可确认生效

【注意】
- 本脚本只改 Docker 引擎配置，不动项目任何代码
- 如果公司网络有代理，请先把代理配置补进 daemon.json 的 proxies 段
================================================================
#>

$ErrorActionPreference = 'Stop'

Write-Host "================================================" -ForegroundColor Cyan
Write-Host " Docker 镜像加速配置" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 1. 定位源文件与目标路径 ----------
$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceJson  = Join-Path $scriptDir 'daemon.json'
$dockerDir   = Join-Path $env:USERPROFILE '.docker'
$targetJson  = Join-Path $dockerDir 'daemon.json'

if (-not (Test-Path $sourceJson)) {
    Write-Host "[错误] 找不到 $sourceJson" -ForegroundColor Red
    Write-Host "       请确认本脚本与 daemon.json 在同一个目录下。" -ForegroundColor Red
    exit 1
}

Write-Host "[1/4] 源配置： $sourceJson"

# ---------- 2. 备份已有配置 ----------
if (Test-Path $targetJson) {
    $backup = "$targetJson.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item $targetJson $backup -Force
    Write-Host "[2/4] 已备份原配置到： $backup" -ForegroundColor Yellow
} else {
    Write-Host "[2/4] 未发现已有配置，将新建" -ForegroundColor Yellow
}

# ---------- 3. 写入新配置 ----------
if (-not (Test-Path $dockerDir)) {
    New-Item -ItemType Directory -Path $dockerDir -Force | Out-Null
}
Copy-Item $sourceJson $targetJson -Force
Write-Host "[3/4] 已写入： $targetJson" -ForegroundColor Green

# ---------- 4. 重启 Docker 引擎 ----------
Write-Host "[4/4] 正在重启 Docker 引擎（约需 20~60 秒）..." -ForegroundColor Cyan
try {
    # 优先用 Docker Desktop 自带 CLI 重启，最稳妥
    $desktopCli = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $desktopCli) {
        Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
        Start-Process $desktopCli
        Write-Host "      已重启 Docker Desktop，请等待右下角小鲸鱼图标变绿。" -ForegroundColor Yellow
    } else {
        Write-Host "      未找到 Docker Desktop.exe，请手动重启 Docker Desktop。" -ForegroundColor Yellow
    }
} catch {
    Write-Host "      自动重启失败（$($_.Exception.Message)），请手动重启 Docker Desktop。" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " 配置完成。等 Docker 起来后，执行下面命令验证：" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  docker info" -ForegroundColor White
Write-Host ""
Write-Host "  在输出的末尾应该能看到（Registry Mirrors）：" -ForegroundColor Gray
Write-Host "    https://docker.1ms.run/" -ForegroundColor DarkGray
Write-Host "    https://docker.m.daocloud.io/" -ForegroundColor DarkGray
Write-Host "    https://docker.xuanyuan.me/" -ForegroundColor DarkGray
Write-Host "    https://dockerproxy.net/" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  然后测试拉取速度（示例）：" -ForegroundColor White
Write-Host "    docker pull nginx:alpine" -ForegroundColor DarkGray
Write-Host ""
