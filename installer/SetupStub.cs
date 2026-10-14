// Self-extracting launcher for Kali Linux Windows Substitute.
//
// The directory produced by build.ps1 is embedded as a zip named
// "<AppName>.payload". On run we extract it to a temporary folder and hand off
// to setup\Setup.cmd, which performs the actual install in PowerShell.
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

            string setup = Path.Combine(extractDir, "setup", "Setup.cmd");
            if (!File.Exists(setup))
            {
                Fail("The installer is incomplete (Setup.cmd not found).");
                return 1;
            }

            var start = new ProcessStartInfo
            {
                FileName = setup,
                Arguments = string.Format("-AppSource \"{0}\"", Path.Combine(extractDir, "app")),
                UseShellExecute = true,
                Verb = "open",
            };
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
