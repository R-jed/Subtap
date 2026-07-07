class Subtap < Formula
  include Language::Python::Virtualenv

  desc "本地优先的 AI 字幕生成引擎 — TUI 界面，端到端转录"
  homepage "https://github.com/R-jed/Subtap"
  url "https://files.pythonhosted.org/packages/source/s/subtap/subtap-0.1.0.tar.gz"
  sha256 "PLACEHOLDER"  # 发布后替换为实际值
  license "MIT"

  depends_on "python@3.12"
  depends_on "ffmpeg"  # pydub 依赖

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"subtap", "--version"
  end
end
