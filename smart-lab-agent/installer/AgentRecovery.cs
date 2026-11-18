using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32;

internal static class AgentRecovery
{
    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool GetTokenInformation(IntPtr token, int informationClass,
        IntPtr buffer, int bufferLength, out int needed);

    private static string GetLogonId()
    {
        const int TokenStatistics = 10;
        int needed;
        using (var identity = WindowsIdentity.GetCurrent())
        {
            GetTokenInformation(identity.Token, TokenStatistics, IntPtr.Zero, 0, out needed);
            if (needed < 16)
                return null;
            var buffer = Marshal.AllocHGlobal(needed);
            try
            {
                if (!GetTokenInformation(identity.Token, TokenStatistics, buffer, needed, out needed))
                    return null;
                // TOKEN_STATISTICS begins with TokenId and AuthenticationId (two LUIDs).
                return Marshal.ReadInt64(buffer, 8).ToString("X16");
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }
    }

    private static int Main(string[] args)
    {
        var agentPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "SmartLabDevice.exe");
        using (var machine = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
        using (var settings = machine.OpenSubKey(@"Software\Smart Lab\Device Agent"))
        {
            if (settings == null || !string.Equals(settings.GetValue("RecoveryAgentPath") as string,
                agentPath, StringComparison.OrdinalIgnoreCase) || !File.Exists(agentPath))
                return 0;
        }

        int sessionId;
        using (var current = Process.GetCurrentProcess())
            sessionId = current.SessionId;

        var logonId = GetLogonId();
        if (logonId == null)
            return 1;
        const string stateKey = @"Software\Smart Lab\Agent Recovery Logon State";
        var marker = "Session" + sessionId;
        try
        {
            if (args.Length == 1 && args[0] == "--arm")
            {
                // Logon IDs can be reused after reboot. Volatile state cannot survive reboot.
                using (var state = Registry.CurrentUser.CreateSubKey(stateKey,
                    RegistryKeyPermissionCheck.ReadWriteSubTree, RegistryOptions.Volatile))
                    state.SetValue(marker, logonId, RegistryValueKind.String);
                return 0;
            }
            using (var state = Registry.CurrentUser.OpenSubKey(stateKey))
                if (state == null || state.GetValue(marker) as string != logonId)
                    return 0;
        }
        catch (IOException) { return 1; }
        catch (UnauthorizedAccessException) { return 1; }
        catch (System.Security.SecurityException) { return 1; }

        var running = false;
        foreach (var process in Process.GetProcessesByName("SmartLabDevice"))
        {
            using (process)
            {
                try
                {
                    if (process.SessionId == sessionId && string.Equals(
                        process.MainModule.FileName, agentPath, StringComparison.OrdinalIgnoreCase))
                        running = true;
                }
                catch (InvalidOperationException) { }
                catch (Win32Exception) { }
            }
        }
        if (running)
            return 0;

        try
        {
            using (Process.Start(new ProcessStartInfo(agentPath) { UseShellExecute = false })) { }
            return 0;
        }
        catch (Win32Exception)
        {
            return 1;
        }
    }
}
