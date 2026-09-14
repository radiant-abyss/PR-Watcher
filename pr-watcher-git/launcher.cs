// PR Watcher portable launcher: starts pr_watcher.py from the SAME folder as this exe.
// Compile: csc /nologo /target:winexe /r:System.Windows.Forms.dll /out:PRWatcher.exe launcher.cs
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

public static class Launcher
{
    static string dir = ".";

    static void Log(string msg)
    {
        try
        {
            File.AppendAllText(Path.Combine(dir, "launcher.log"),
                DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + msg + "\r\n");
        }
        catch (Exception) { }
    }

    static void Fail(string msg)
    {
        Log("FAIL " + msg.Replace("\r\n", " | "));
        try
        {
            MessageBox.Show(msg, "PR Watcher", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        catch (Exception) { }
    }

    public static void Main()
    {
        dir = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);

        string script = Path.Combine(dir, "pr_watcher.py");
        if (!File.Exists(script))
        {
            Fail("找不到 pr_watcher.py。\r\n\r\n请保持本 exe 与 pr_watcher.py 在同一文件夹内:\r\n" + dir);
            return;
        }

        // Prefer a pythonw shipped next to the exe, then PATH.
        string local = Path.Combine(dir, "pythonw.exe");
        string[] candidates = File.Exists(local) ? new string[] { local }
                                                 : new string[] { "pythonw.exe", "python.exe" };

        string lastError = "";
        foreach (string exe in candidates)
        {
            try
            {
                Process p = new Process();
                p.StartInfo.FileName = exe;
                p.StartInfo.Arguments = "\"" + script + "\"";
                p.StartInfo.WorkingDirectory = dir;
                p.StartInfo.UseShellExecute = true;
                p.Start();
                Log("started " + exe + " \"" + script + "\" pid=" + p.Id);

                // Give it a moment: a crash (missing requests / config error) shows up fast.
                if (p.WaitForExit(2500) && p.ExitCode != 0)
                {
                    lastError = exe + " 退出码 " + p.ExitCode;
                    Log("nonzero exit: " + lastError);
                    continue;
                }
                return;   // running (or exited cleanly = another instance already active)
            }
            catch (Exception ex)
            {
                lastError = exe + ": " + ex.Message;
                Log(lastError);
            }
        }

        Fail("无法启动 PR Watcher。\r\n\r\n最后错误: " + lastError +
             "\r\n\r\n请检查:\r\n 1) 已安装 Python 3 并加入 PATH (python --version)\r\n" +
             " 2) 已执行 pip install requests\r\n" +
             " 3) 在文件夹内手动运行 python pr_watcher.py --selftest 查看原因");
    }
}
