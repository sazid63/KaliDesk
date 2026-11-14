// Self-extracting launcher for Kali Linux Windows Substitute.
//
// The directory produced by build.ps1 is embedded as a zip named
// "<AppName>.payload". On run we extract it to a temporary folder and hand off
// to setup\Wizard.ps1, the graphical setup wizard (which in turn calls
// Install.ps1). If the wizard is somehow missing we fall back to the silent
// setup\Setup.cmd.
//
// The wizard's exit code is read back: 0 and 1223 (cancelled) end quietly, any
// other code shows a message box that points at the log. The log is
// %TEMP%\KaliDesk-Setup.log.
//
// This stub does no network access and writes only to the user's temp folder.
// Written for the .NET Framework 4 csc.exe (C# 5): no newer syntax.

using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

internal static class SetupStub
{
    private const string PayloadName = "KaliWindowsSubstitute.payload";
    private const string AppTitle = "Kali Linux Windows Substitute";
    // ERROR_CANCELLED: the wizard was cancelled. Not treated as a failure.
    private const int ExitCancelled = 1223;

    private static readonly string LogPath = Path.Combine(Path.GetTempPath(), "KaliDesk-Setup.log");

    [STAThread]
    private static int Main(string[] args)
    {
        string staging = Path.Combine(
            Path.GetTempPath(),
            "KWS-Setup-" + Guid.NewGuid().ToString("N"));
        Log("setup started; staging " + staging);

        try
        {
            Directory.CreateDirectory(staging);

            string zipPath = Path.Combine(staging, "payload.zip");
            Assembly assembly = Assembly.GetExecutingAssembly();
            using (Stream resource = assembly.GetManifestResourceStream(PayloadName))
            {
                if (resource == null)
                {
                    return Fail("The installer payload is missing or corrupt.");
                }
                using (FileStream output = File.Create(zipPath))
                {
                    resource.CopyTo(output);
                }
            }

            string extractDir = Path.Combine(staging, "files");
            using (ZipArchive archive = ZipFile.OpenRead(zipPath))
            {
                archive.ExtractToDirectory(extractDir);
            }

            string appSource = Path.Combine(extractDir, "app");
            string wizard = Path.Combine(extractDir, "setup", "Wizard.ps1");
            string setupCmd = Path.Combine(extractDir, "setup", "Setup.cmd");

            ProcessStartInfo start;
            if (File.Exists(wizard))
            {
                start = new ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = string.Format(
                        "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"{0}\" -AppSource \"{1}\"",
                        wizard, appSource),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
            }
            else if (File.Exists(setupCmd))
            {
                start = new ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = string.Format("/c \"\"{0}\" -AppSource \"{1}\"\"", setupCmd, appSource),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
            }
            else
            {
                return Fail("The installer is incomplete (no setup wizard found).");
            }

            Log("starting " + start.FileName + " " + start.Arguments);
            using (Process process = Process.Start(start))
            {
                if (process == null)
                {
                    return Fail("The installer could not start the setup step.");
                }
                process.WaitForExit();
                int code = process.ExitCode;
                Log("setup step exited with code " + code);

                if (code == 0 || code == ExitCancelled)
                {
                    return code;
                }
                return Fail(string.Format(
                    "Setup did not finish (exit code {0}).\n\nDetails are in:\n{1}",
                    code, LogPath));
            }
        }
        catch (Exception ex)
        {
            Log("error: " + ex);
            return Fail("Setup failed: " + ex.Message + "\n\nDetails are in:\n" + LogPath);
        }
        finally
        {
            try { Directory.Delete(staging, true); } catch { /* best effort */ }
            Log("setup finished");
        }
    }

    // Shows the error to the user and returns the exit code to report.
    private static int Fail(string message)
    {
        Log("FAILED: " + message.Replace("\n", " "));
        MessageBox.Show(message, AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
        return 1;
    }

    private static void Log(string message)
    {
        try
        {
            File.AppendAllText(
                LogPath,
                DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + message + Environment.NewLine);
        }
        catch
        {
            // Logging is best effort; it must never stop setup.
        }
    }
}
