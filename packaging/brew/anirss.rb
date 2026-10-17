class Anirss < Formula
  desc "Search nyaa.si and hand the result to qBittorrent"
  homepage "https://github.com/marcusbandit/anirss"
  url "https://github.com/marcusbandit/anirss/archive/refs/tags/v0.4.1.tar.gz"
  sha256 "41abedaa11ae5955081d2883c8e0d6723334ba08f2c5d1d1c882ab94e903d2f3"
  license "GPL-3.0-or-later"
  head "https://github.com/marcusbandit/anirss.git", branch: "main"

  depends_on "fzf"
  depends_on "python@3.13"

  def install
    python = Formula["python@3.13"].opt_bin/"python3.13"
    inreplace "anirss", "#!/usr/bin/env python3", "#!#{python}"
    # Launcher and library live side-by-side; the launcher uses
    # `os.path.realpath(__file__)` to find anirss_lib next to itself.
    libexec.install "anirss", "anirss_lib"
    bin.install_symlink libexec/"anirss"
    zsh_completion.install "completions/_anirss"
    bash_completion.install "completions/anirss.bash" => "anirss"
  end

  test do
    assert_equal "anirss #{version}", shell_output("#{bin}/anirss --version").strip
    # Completion files were installed.
    assert_predicate zsh_completion/"_anirss", :exist?
    assert_predicate bash_completion/"anirss", :exist?
  end
end
