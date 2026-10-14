// Self-extracting launcher for Kali Linux Windows Substitute.
//
// The directory produced by build.ps1 is embedded as a zip named
// "<AppName>.payload". On run we extract it to a temporary folder and hand off
// to setup\Wizard.ps1, the graphical setup wizard (which in turn calls
// Install.ps1). If the wizard is somehow missing we fall back to the silent
// setup\Setup.cmd.
//
// This stub does no network access and writes only to the user's temp folder.

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

    [STAThread]
    private static int Main(string[] args)
    {
        string staging = Path.Combine(
            Path.GetTempPath(),
            "KWS-Setup-" + Guid.NewGuid().ToString("N"));

        try
        {
            Directory.CreateDirectory(staging);

            string zipPath = Path.Combine(staging, "payload.zip");
            Assembly assembly = Assembly.GetExecutingAssembly();
            using (Stream resource = assembly.GetManifestResourceStream(PayloadName))
            {
                if (resource == null)
                {
                    Fail("The installer payload is missing or corrupt.");
                    return 1;
                }
                using (FileStream output = File.Create(zipPath))
                {
                    resource.CopyTo(output);
                }
            }

            string extractDir = Path.Combine(staging, "files");
            ZipFile.ExtractToDirectory(zipPath, extractDir);

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
                    UseShellExecute = true,
                    Verb = "open",
                    WindowStyle = ProcessWindowStyle.Hidden,
                };
            }
            else if (File.Exists(setupCmd))
            {
                start = new ProcessStartInfo
                {
                    FileName = setupCmd,
                    Arguments = string.Format("-AppSource \"{0}\"", appSource),
                    UseShellExecute = true,
                    Verb = "open",
                };
            }
            else
            {
                Fail("The installer is incomplete (no setup wizard found).");
                return 1;
            }

            Process process = Process.Start(start);
            if (process == null)
            {
                Fail("The installer could not start the setup step.");
                return 1;
            }
            process.WaitForExit();
            return process.ExitCode;
        }
        catch (Exception ex)
        {
            Fail(ex.Message);
            return 1;
        }
        finally
        {
            try { Directory.Delete(staging, true); } catch { /* best effort */ }
        }
    }

    private static void Fail(string message)
    {
        MessageBox.Show(message, AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
