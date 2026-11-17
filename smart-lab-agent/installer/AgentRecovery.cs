using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;

internal static class AgentRecovery
{
    private static int Main()
    {
        var agentPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "SmartLabDevice.exe");
        if (!File.Exists(agentPath))
            return 0;

        int sessionId;
        using (var current = Process.GetCurrentProcess())
            sessionId = current.SessionId;

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
