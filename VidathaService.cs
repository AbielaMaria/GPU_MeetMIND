// using System;
// using System.Diagnostics;
// using System.IO;
// using System.ServiceProcess;
// using System.Timers;

// public class VidathaService : ServiceBase
// {
//     private Process backend;
//     private Timer monitor;
//     private readonly object logLock = new object();

//     private const string Root = @"F:\MeetNotes\MeetNotes";
//     private const string BackendDir = Root + @"\backend";
//     private const string Python = BackendDir + @"\.venv311\Scripts\python.exe";
//     private const string CertDir = @"C:\Users\Cdac\GPU_MeetMIND_certs";
//     private const string KeyFile = CertDir + @"\meetmind-key.pem";
//     private const string CertFile = CertDir + @"\meetmind-cert.pem";
//     private const string LogDir = Root + @"\logs";
//     private const string ServiceLog = LogDir + @"\vidatha-service.log";
//     private const string StdoutLog = LogDir + @"\vidatha-service-stdout.log";
//     private const string StderrLog = LogDir + @"\vidatha-service-stderr.log";

//     public VidathaService()
//     {
//         ServiceName = "VidathaBackend";
//         CanStop = true;
//         CanShutdown = true;
//         AutoLog = false;
//     }

//     private void Log(string message)
//     {
//         lock (logLock)
//         {
//             Directory.CreateDirectory(LogDir);
//             File.AppendAllText(
//                 ServiceLog,
//                 "[" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") +
//                 "] " + message + Environment.NewLine
//             );
//         }
//     }

//     protected override void OnStart(string[] args)
//     {
//         Directory.CreateDirectory(LogDir);
//         Log("Vidatha Windows Service starting.");

//         if (!File.Exists(Python) ||
//             !File.Exists(KeyFile) ||
//             !File.Exists(CertFile))
//         {
//             Log("ERROR: Python or SSL certificate file is missing.");
//             throw new InvalidOperationException(
//                 "Python or SSL certificate file is missing."
//             );
//         }

//         backend = new Process();

//         backend.StartInfo = new ProcessStartInfo
//         {
//             FileName = Python,
//             WorkingDirectory = BackendDir,
//             Arguments =
//                 "-u -m uvicorn app:app " +
//                 "--host 0.0.0.0 --port 8100 " +
//                 "--ssl-keyfile \"" + KeyFile + "\" " +
//                 "--ssl-certfile \"" + CertFile + "\"",
//             UseShellExecute = false,
//             CreateNoWindow = true,
//             RedirectStandardOutput = true,
//             RedirectStandardError = true
//         };

//         backend.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
//         {
//             if (e.Data != null)
//                 AppendOutput(StdoutLog, e.Data);
//         };

//         backend.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
//         {
//             if (e.Data != null)
//                 AppendOutput(StderrLog, e.Data);
//         };

//         if (!backend.Start())
//             throw new InvalidOperationException("Could not start Vidatha backend.");

//         backend.BeginOutputReadLine();
//         backend.BeginErrorReadLine();

//         monitor = new Timer(2000);
//         monitor.AutoReset = true;
//         monitor.Elapsed += delegate(object sender, ElapsedEventArgs e)
//         {
//             try
//             {
//                 if (backend != null && backend.HasExited)
//                 {
//                     Log("Backend exited unexpectedly. Restarting service.");
//                     Environment.Exit(1);
//                 }
//             }
//             catch (Exception ex)
//             {
//                 Log("Monitor error: " + ex.Message);
//             }
//         };
//         monitor.Start();

//         Log("Backend process launched. PID: " + backend.Id);
//     }

//     private void AppendOutput(string path, string line)
//     {
//         lock (logLock)
//         {
//             File.AppendAllText(
//                 path,
//                 "[" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") +
//                 "] " + line + Environment.NewLine
//             );
//         }
//     }

//     protected override void OnStop()
//     {
//         Log("Vidatha Windows Service stopping.");

//         if (monitor != null)
//         {
//             monitor.Stop();
//             monitor.Dispose();
//             monitor = null;
//         }

//         if (backend != null)
//         {
//             try
//             {
//                 if (!backend.HasExited)
//                 {
//                     backend.Kill();
//                     backend.WaitForExit(10000);
//                 }
//             }
//             catch (Exception ex)
//             {
//                 Log("Error stopping backend: " + ex.Message);
//             }

//             backend.Dispose();
//             backend = null;
//         }

//         Log("Vidatha Windows Service stopped.");
//     }

//     protected override void OnShutdown()
//     {
//         OnStop();
//         base.OnShutdown();
//     }

//     public static void Main()
//     {
//         ServiceBase.Run(new VidathaService());
//     }
// }


using System;
using System.Diagnostics;
using System.IO;
using System.ServiceProcess;
using System.Timers;

public class VidathaService : ServiceBase
{
    private Process backend;
    private Timer monitor;
    private readonly object logLock = new object();

    private const string Root = @"F:\MeetNotes\MeetNotes";
    private const string BackendDir = Root + @"\backend";
    private const string Python = BackendDir + @"\.venv311\Scripts\python.exe";

    private const string CertDir = @"C:\Users\Cdac\GPU_MeetMIND_certs";
    private const string KeyFile = CertDir + @"\meetmind-key.pem";
    private const string CertFile = CertDir + @"\meetmind-cert.pem";

    private const string LogDir = Root + @"\logs";
    private const string ServiceLog = LogDir + @"\vidatha-service.log";
    private const string StdoutLog = LogDir + @"\vidatha-service-stdout.log";
    private const string StderrLog = LogDir + @"\vidatha-service-stderr.log";

    private readonly Stopwatch serviceTimer = new Stopwatch();
    private readonly Stopwatch startupTimer = new Stopwatch();

    public VidathaService()
    {
        ServiceName = "VidathaBackend";
        CanStop = true;
        CanShutdown = true;
        AutoLog = false;
    }

    private string Timestamp()
    {
        return DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
    }

    private void Log(string message)
    {
        lock (logLock)
        {
            Directory.CreateDirectory(LogDir);

            File.AppendAllText(
                ServiceLog,
                "[" + Timestamp() + "] " + message +
                Environment.NewLine
            );
        }
    }

    private void AppendOutput(string path, string source, string line)
    {
        lock (logLock)
        {
            Directory.CreateDirectory(LogDir);

            File.AppendAllText(
                path,
                "[" + Timestamp() + "] [" + source + "] " + line +
                Environment.NewLine
            );
        }
    }

    protected override void OnStart(string[] args)
    {
        startupTimer.Restart();

        Directory.CreateDirectory(LogDir);

        Log("==================================================");
        Log("VIDATHA BACKEND SERVICE STARTING");
        Log("Machine: " + Environment.MachineName);
        Log("Account: " + Environment.UserName);
        Log("Process ID: " + Process.GetCurrentProcess().Id);
        Log("Python: " + Python);
        Log("Backend directory: " + BackendDir);
        Log("Port: 8100");
        Log("HTTPS: Enabled");
        Log("Reload: Disabled");
        Log("==================================================");

        if (!File.Exists(Python) ||
            !File.Exists(KeyFile) ||
            !File.Exists(CertFile))
        {
            Log("ERROR: Python or SSL certificate file is missing.");
            throw new InvalidOperationException(
                "Python or SSL certificate file is missing."
            );
        }

        Log("Python executable verified.");
        Log("SSL certificate files verified.");

        backend = new Process();

        backend.StartInfo = new ProcessStartInfo
        {
         FileName = Python,
    WorkingDirectory = BackendDir,

    Arguments =
        "-u -m uvicorn app:app " +
        "--host 0.0.0.0 --port 8100 " +
        "--ssl-keyfile \"" + KeyFile + "\" " +
        "--ssl-certfile \"" + CertFile + "\"",

    UseShellExecute = false,
    CreateNoWindow = true,
    RedirectStandardOutput = true,
    RedirectStandardError = true,

    // Read Python output as UTF-8
    StandardOutputEncoding = new System.Text.UTF8Encoding(false),
    StandardErrorEncoding = new System.Text.UTF8Encoding(false)
};
        backend.OutputDataReceived += delegate(
            object sender,
            DataReceivedEventArgs e)
        {
            if (e.Data != null)
                AppendOutput(StdoutLog, "STDOUT", e.Data);
        };

        backend.ErrorDataReceived += delegate(
            object sender,
            DataReceivedEventArgs e)
        {
            if (e.Data != null)
                AppendOutput(StderrLog, "STDERR", e.Data);
        };

        Log("Starting Python backend process.");

        if (!backend.Start())
            throw new InvalidOperationException(
                "Could not start Vidatha backend."
            );

        Log("Python backend process started.");
        Log("Backend PID: " + backend.Id);
        Log("Backend executable: " + backend.StartInfo.FileName);
        Log("Backend working directory: " + backend.StartInfo.WorkingDirectory);
        Log("Startup elapsed: " +
            startupTimer.ElapsedMilliseconds + " ms");

        backend.BeginOutputReadLine();
        backend.BeginErrorReadLine();

        serviceTimer.Start();

        monitor = new Timer(2000);
        monitor.AutoReset = true;

        monitor.Elapsed += delegate(
            object sender,
            ElapsedEventArgs e)
        {
            try
            {
                if (backend != null && backend.HasExited)
                {
                    Log("ERROR: Backend process exited.");
                    Log("Backend PID: " + backend.Id);
                    Log("Exit code: " + backend.ExitCode);
                    Log("Service uptime: " +
                        serviceTimer.Elapsed.ToString());

                    Environment.Exit(1);
                }
            }
            catch (Exception ex)
            {
                Log("Monitor error: " + ex);
            }
        };

        monitor.Start();

        Log("Backend monitoring started.");
        Log("VIDATHA BACKEND SERVICE STARTED SUCCESSFULLY.");
    }

    protected override void OnStop()
    {
        Log("VIDATHA BACKEND SERVICE STOPPING.");

        serviceTimer.Stop();

        Log("Total service uptime: " +
            serviceTimer.Elapsed.ToString());

        if (monitor != null)
        {
            monitor.Stop();
            monitor.Dispose();
            monitor = null;
        }

        if (backend != null)
        {
            try
            {
                if (!backend.HasExited)
                {
                    Log("Stopping backend PID: " + backend.Id);

                    backend.Kill();
                    backend.WaitForExit(10000);

                    Log("Backend process stopped. Exit code: " +
                        backend.ExitCode);
                }
            }
            catch (Exception ex)
            {
                Log("Error stopping backend: " + ex);
            }

            backend.Dispose();
            backend = null;
        }

        Log("VIDATHA BACKEND SERVICE STOPPED.");
        Log("==================================================");
    }

    protected override void OnShutdown()
    {
        OnStop();
        base.OnShutdown();
    }

    public static void Main()
    {
        ServiceBase.Run(new VidathaService());
    }
}
