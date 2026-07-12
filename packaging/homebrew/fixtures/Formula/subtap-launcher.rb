class SubtapLauncher < Formula
  desc "Local-first TUI subtitle tool — locked-runtime launcher"
  homepage "https://github.com/anthropics/subtap"
  # TODO: fill in URL and SHA256 from release build
  url "https://TODO.example.com/subtap-launcher-0.0.0.tar.gz"
  sha256 "TODO_SHA256_PLACEHOLDER"
  license "MIT"

  depends_on arch: :arm64
  depends_on "uv"
  depends_on "ffmpeg"

  def install
    # 安装启动器脚本
    bin.install "launcher/subtap"

    # 安装版本清单和依赖清单到 share/subtap/
    (share/"subtap").install "version.txt"
    (share/"subtap").install "runtime-requirements.txt"
  end

  test do
    # 仅验证 --bootstrap-info 不触发初始化
    output = shell_output("#{bin}/subtap --bootstrap-info")
    assert_match "initialized=false", output
  end
end
