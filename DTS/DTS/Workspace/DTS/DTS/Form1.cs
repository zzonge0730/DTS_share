using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Globalization;
using System.IO;
using System.Xml.Linq;
using System.Net;
using System.Net.Sockets;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Threading;


namespace DTS
{
    public partial class Form1 : Form
    {
        public static Form1 form;

        TCP_Client_Manager visionclient;
        List<Pose> Poses = new List<Pose>();

        private static readonly Dictionary<string, string> AppSettings = LoadAppSettings();
        private static readonly string VisionIp = ReadStringSetting("VISION_IP", "172.21.135.200");
        private static readonly string VisionPort = ReadStringSetting("VISION_PORT", "50001");
        private static readonly string RobotIp = ReadStringSetting("ROBOT_IP", "172.21.135.200");
        private static readonly int RobotPort = ReadIntSetting("ROBOT_PORT", 2000);
        private static readonly string MyIp = ReadStringSetting("MY_IP", "172.21.128.1");
        private static readonly int MyPort = ReadIntSetting("MY_PORT", 2001);
        private static readonly int PosesPerPacket = ReadIntSetting("POSES_PER_PACKET", 3);
        private static readonly bool PadLastPacket = ReadBoolSetting("PAD_LAST_PACKET", true);
        private static readonly string CntFieldMode = ReadStringSetting("CNT_FIELD_MODE", "packet");
        private static readonly double MaxTol = ReadDoubleSetting("MAX_TOL", 2.0);
        private static readonly double AvgTol = ReadDoubleSetting("AVG_TOL", 1.0);
        private static readonly string GapMode = ReadStringSetting("GAP_MODE", "random");
        private static readonly string GapJsonPathSetting = ReadRawStringSetting("GAP_JSON_PATH", "gap_input.json");
        private static readonly int GapMaxAgeMs = ReadIntSetting("GAP_MAX_AGE_MS", 5000);
        private static readonly bool GapAllowLegacyRandom = ReadBoolSetting("GAP_ALLOW_LEGACY_RANDOM", false);
        private static readonly bool IcpQualityEnforce = ReadBoolSetting("ICP_QUALITY_ENFORCE", false);
        private static readonly double IcpFitnessMin = ReadDoubleSetting("ICP_FITNESS_MIN", 0.3);
        private static readonly double IcpInlierRmseMax = ReadDoubleSetting("ICP_INLIER_RMSE_MAX", 1.5);
        private static readonly Random GapRandom = new Random();
        private static readonly bool StatusEnable = ReadBoolSetting("STATUS_ENABLE", true);
        private static readonly string StatusTargetIp = ReadStringSetting("STATUS_TARGET_IP", "127.0.0.1");
        private static readonly int StatusPort = ReadIntSetting("STATUS_PORT", 2002);
        private static readonly int StatusCooldownMs = ReadIntSetting("STATUS_COOLDOWN_MS", 3000);
        private static readonly bool StatusResendWhileLatched = ReadBoolSetting("STATUS_RESEND_WHILE_LATCHED", false);
        private static readonly bool StatusSendOnStateChange = ReadBoolSetting("STATUS_SEND_ON_STATE_CHANGE", true);
        private static readonly double XMin = ReadDoubleSetting("X_MIN", -5000.0);
        private static readonly double XMax = ReadDoubleSetting("X_MAX", 5000.0);
        private static readonly double YMin = ReadDoubleSetting("Y_MIN", -5000.0);
        private static readonly double YMax = ReadDoubleSetting("Y_MAX", 5000.0);
        private static readonly double ZMin = ReadDoubleSetting("Z_MIN", -5000.0);
        private static readonly double ZMax = ReadDoubleSetting("Z_MAX", 5000.0);
        private static readonly string StartupConfigError = ValidateStartupConfig();
        private static readonly string SessionId = Guid.NewGuid().ToString("N");
        private static readonly string LogRoot = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logs");
        private static string LastRobotMessage = string.Empty;
        // 0=clear, 1=latched. Use Interlocked/Volatile for cross-thread safety.
        private static int StopLatch = 0;
        private static string LastStatusKey = string.Empty;
        private static long LastStatusSentAtMs = 0;
        
        public Form1()
        {
            InitializeComponent();
            form = this;
            LogSettings();
            UpdateConfigLabel();
            UpdateStateLabel("DISCONNECTED");
            ApplyStartupConfigSafety();

        }

        private async void btn_Con_Vision_Click(object sender, EventArgs e)
        {

            if (visionclient == null)
            {
                visionclient = new TCP_Client_Manager();
            }
            else if (visionclient.isClientConnected)
            {
                visionclient.Disconnect();
            }

            await visionclient.ConnectToServer(VisionIp, VisionPort, "vision");
            UpdateStateLabel("VISION_CONNECTED");

        }

        private void btn_Con_Robot_Click(object sender, EventArgs e)
        {
            if (!IsRuntimeConfigValid())
            {
                Console.WriteLine($"[Config] INVALID. Robot connect blocked. reason={StartupConfigError}");
                UpdateStateLabel("CONFIG_ERROR");
                return;
            }

            //string robot_ip = "192.168.10.101"; string robot_port = "50010"; //Robot ip
            //if (robotclient == null)
            //{
            //    robotclient = new TCP_Client_Manager();
            //}

            //robotclient.ConnectToServer(robot_ip, robot_port,"robot");

            UDPSocket.Connect(RobotIp, RobotPort, MyIp, MyPort);
            UpdateStateLabel("ROBOT_CONNECTED");
        }

        private void btn_Send_Pose_Click(object sender, EventArgs e)
        {
            try
            {
                UDPSocket.CloseProcess();
                if (visionclient != null && visionclient.isClientConnected)
                {
                    visionclient.Disconnect();
                }
                Console.WriteLine("[Disconnect] UDP/TCP closed.");
                UpdateStateLabel("DISCONNECTED");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[Disconnect] ERROR: {ex.Message}");
            }
        }

        public async void Handle_Robot(string message)
        {
            try
            {
                LastRobotMessage = message;
                Console.WriteLine(message);
                string[] cmd = message.Split(',');
                cmd[0] = cmd[0].Replace("\n\0", "");
                Console.WriteLine(cmd[0]);

                if (cmd[0] == "READY")
                {
                    if (!IsRuntimeConfigValid())
                    {
                        Console.WriteLine($"[Config] INVALID. READY ignored. reason={StartupConfigError}");
                        SendStatusOnce("1004", "CONFIG_INVALID", null, null);
                        return;
                    }
                    if (Volatile.Read(ref StopLatch) == 1)
                    {
                        Console.WriteLine("[StopLatch] Active. READY ignored.");
                        SendStatusOnce("2002", "LATCHED", null, null);
                        return;
                    }
                    if (visionclient != null && visionclient.isClientConnected)
                    {
                        await visionclient.SendMessageToServer(cmd[0]);
                    }
                    else
                    {
                        Console.WriteLine("[Vision] Not connected. Skip READY forward.");
                        SendStatusOnce("1004", "NO_VISION", null, null);
                    }

                    //UDPSocket.SendData("OK");
                    //UDPSocket.SendData("1100,0002,816.072,757.341,76.977,-90.762,88.375,-0.116,816.072,757.341,76.977,-90.762,88.375,-0.116");
                    //UDPSocket.SendData("1100,0001,-59.384,137.852,-69.201,1.81100,-69.379,-51.759");
                    //UDPSocket.SendData("1100,0001,-28.863,150.140,-58.549,0.54600,-92.851,-23.906");
                }
                Console.WriteLine($"[Robot] Receive Message : {message}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"ERROR : {ex}");
            }
        }
        public  void Handle_Vision(string message)
        {
            try
            {
                string normalized = (message ?? string.Empty).Trim();
                string[] cmd = normalized.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                if (cmd.Length < 2)
                {
                    TriggerSafetyLatch("VISION_PROTOCOL_UNKNOWN", "[Vision] malformed payload (fields<2)");
                    return;
                }

                if (!string.Equals(cmd[0], "1100", StringComparison.Ordinal))
                {
                    TriggerSafetyLatch("VISION_PROTOCOL_UNKNOWN", $"[Vision] unexpected header={cmd[0]}");
                    return;
                }

                if (!int.TryParse(cmd[1], out int cnt) || cnt <= 0)
                {
                    TriggerSafetyLatch("VISION_PROTOCOL_UNKNOWN", $"[Vision] invalid count={cmd[1]}");
                    return;
                }

                int expectedFields = 2 + (cnt * 6);
                if (cmd.Length < expectedFields)
                {
                    TriggerSafetyLatch("VISION_PROTOCOL_UNKNOWN", $"[Vision] payload underflow expected={expectedFields} actual={cmd.Length}");
                    return;
                }

                string onlypose = string.Join(",", cmd, 2, cnt * 6);
                Divide_90_Pose(cnt, onlypose);
                Console.WriteLine($"[Vision] Receive Message : {normalized}");

            }
            catch (Exception ex)
            {
                TriggerSafetyLatch("VISION_PROTOCOL_UNKNOWN", $"[Vision] parse exception: {ex.Message}");
            }
        }

        private void Divide_90_Pose(int cnt, string onlypose)
        {
            try
            {
                Poses.Clear();
                var poseValues = onlypose.Split(',');
                for (int i = 0; i < cnt; i++)
                {
                    int baseIdx = i * 6; // 한 pose는 6개 값
                    if (baseIdx + 5 >= poseValues.Length) break; // 안전 체크

                    double x = double.Parse(poseValues[baseIdx], CultureInfo.InvariantCulture);
                    double y = double.Parse(poseValues[baseIdx + 1], CultureInfo.InvariantCulture);
                    double z = double.Parse(poseValues[baseIdx + 2], CultureInfo.InvariantCulture);
                    double rx = double.Parse(poseValues[baseIdx + 3], CultureInfo.InvariantCulture);
                    double ry = double.Parse(poseValues[baseIdx + 4], CultureInfo.InvariantCulture);
                    double rz = double.Parse(poseValues[baseIdx + 5], CultureInfo.InvariantCulture);

                    Pose pose = new Pose(x, y, z, rx, ry, rz);
                    if (!IsPoseInRange(pose))
                    {
                        TriggerSafetyLatch(
                            "POSE_OUT_OF_RANGE",
                            $"[PoseGuard] out-of-range pose idx={i} x={x:F3} y={y:F3} z={z:F3}"
                        );
                        return;
                    }
                    Poses.Add(pose);
                }

                // 3개 pose 단위로 전송 (3의 배수가 아니면 마지막 pose로 패딩)
                var gapResult = EvaluateGap(Poses.Count);
                Console.WriteLine($"[Gap] result={gapResult.Result} max={gapResult.MaxGap:F3} avg={gapResult.AvgGap:F3} rms={gapResult.RmsGap:F3} tol_max={MaxTol:F3} tol_avg={AvgTol:F3} reason={gapResult.Reason}");
                if (gapResult.Result == "NG")
                {
                    Interlocked.Exchange(ref StopLatch, 1);
                    UpdateStatusLatchUi(true);
                    Console.WriteLine("[Gap] NG detected. Pose send blocked.");
                    SendStatusOnce("2002", gapResult.Reason, gapResult.MaxGap, gapResult.AvgGap);
                    WriteNgLog(gapResult, BuildPlannedPayloads(Poses));
                    UpdateLastNgLabel(gapResult);
                    return;
                }
                SendStatusOnce("2100", "OK", gapResult.MaxGap, gapResult.AvgGap);
                WriteOkLog(gapResult);
                UpdateStateLabel("OK");

                for (int i = 0; i < Poses.Count; i += PosesPerPacket)
                {
                    var batch = Poses.GetRange(i, Math.Min(PosesPerPacket, Poses.Count - i));

                    if (PadLastPacket && batch.Count < PosesPerPacket && batch.Count > 0)
                    {
                        Pose last = batch[batch.Count - 1];
                        while (batch.Count < PosesPerPacket)
                        {
                            batch.Add(last);
                        }
                    }

                    int cntForHeader = (CntFieldMode == "total") ? Poses.Count : batch.Count;
                    string payload = BuildPayload(batch, cntForHeader);
                    Console.WriteLine($"{i} : {payload}");
                    UDPSocket.SendData(payload);

                    Console.WriteLine($"[{i / PosesPerPacket + 1}] batch 전송 완료, 개수={batch.Count}");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine(ex.Message);
            }
        }

        private string BuildPayload(List<Pose> batch, int cntForHeader)
        {
            StringBuilder sb = new StringBuilder();
            sb.Append("1100,");
            sb.Append(cntForHeader.ToString("D4")); // header: pose 개수
            foreach (var p in batch)
            {
                sb.Append(",");
                sb.Append(p.X.ToString("F3", CultureInfo.InvariantCulture));
                sb.Append(",");
                sb.Append(p.Y.ToString("F3", CultureInfo.InvariantCulture));
                sb.Append(",");
                sb.Append(p.Z.ToString("F3", CultureInfo.InvariantCulture));
                sb.Append(",");
                sb.Append(p.Rx.ToString("F3", CultureInfo.InvariantCulture));
                sb.Append(",");
                sb.Append(p.Ry.ToString("F3", CultureInfo.InvariantCulture));
                sb.Append(",");
                sb.Append(p.Rz.ToString("F3", CultureInfo.InvariantCulture));
            }
            return sb.ToString();
        }

        private static Dictionary<string, string> LoadAppSettings()
        {
            var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            try
            {
                string configPath = AppDomain.CurrentDomain.SetupInformation.ConfigurationFile;
                if (!File.Exists(configPath))
                {
                    return result;
                }

                XDocument doc = XDocument.Load(configPath);
                XElement appSettings = doc.Root?.Element("appSettings");
                if (appSettings == null)
                {
                    return result;
                }

                foreach (XElement add in appSettings.Elements("add"))
                {
                    XAttribute keyAttr = add.Attribute("key");
                    XAttribute valueAttr = add.Attribute("value");
                    if (keyAttr == null || valueAttr == null)
                    {
                        continue;
                    }
                    result[keyAttr.Value] = valueAttr.Value;
                }
            }
            catch
            {
                return result;
            }

            return result;
        }

        private static int ReadIntSetting(string key, int defaultValue)
        {
            if (AppSettings.TryGetValue(key, out string value) && int.TryParse(value, out int parsed))
            {
                return parsed;
            }
            return defaultValue;
        }

        private static bool ReadBoolSetting(string key, bool defaultValue)
        {
            if (AppSettings.TryGetValue(key, out string value) && bool.TryParse(value, out bool parsed))
            {
                return parsed;
            }
            return defaultValue;
        }

        private static string ReadStringSetting(string key, string defaultValue)
        {
            if (AppSettings.TryGetValue(key, out string value) && !string.IsNullOrWhiteSpace(value))
            {
                return value.Trim().ToLowerInvariant();
            }
            return defaultValue;
        }

        private static string ReadRawStringSetting(string key, string defaultValue)
        {
            if (AppSettings.TryGetValue(key, out string value) && !string.IsNullOrWhiteSpace(value))
            {
                return value.Trim();
            }
            return defaultValue;
        }

        private static double ReadDoubleSetting(string key, double defaultValue)
        {
            if (AppSettings.TryGetValue(key, out string value) &&
                double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out double parsed))
            {
                return parsed;
            }
            return defaultValue;
        }

        private static void LogSettings()
        {
            Console.WriteLine($"[Config] POSES_PER_PACKET={PosesPerPacket} PAD_LAST_PACKET={PadLastPacket} CNT_FIELD_MODE={CntFieldMode}");
            Console.WriteLine($"[Config] MAX_TOL={MaxTol:F3} AVG_TOL={AvgTol:F3} GAP_MODE={GapMode}");
            Console.WriteLine($"[Config] POSE_RANGE X=[{XMin:F3},{XMax:F3}] Y=[{YMin:F3},{YMax:F3}] Z=[{ZMin:F3},{ZMax:F3}]");
            Console.WriteLine($"[Config] GAP_JSON_PATH={ResolveGapJsonPath()} GAP_MAX_AGE_MS={GapMaxAgeMs} GAP_ALLOW_LEGACY_RANDOM={GapAllowLegacyRandom}");
            Console.WriteLine($"[Config] ICP_QUALITY_ENFORCE={IcpQualityEnforce} ICP_FITNESS_MIN={IcpFitnessMin:F3} ICP_INLIER_RMSE_MAX={IcpInlierRmseMax:F3}");
            Console.WriteLine($"[Config] STATUS_ENABLE={StatusEnable}");
            Console.WriteLine($"[Config] STATUS_TARGET={StatusTargetIp}:{StatusPort}");
            Console.WriteLine($"[Config] STATUS_COOLDOWN_MS={StatusCooldownMs} RESEND_LATCHED={StatusResendWhileLatched} SEND_ON_CHANGE={StatusSendOnStateChange}");
            Console.WriteLine($"[Config] SESSION_ID={SessionId}");
            if (string.IsNullOrWhiteSpace(StartupConfigError))
            {
                Console.WriteLine("[Config] startup validation=OK");
            }
            else
            {
                Console.WriteLine($"[Config] startup validation=FAIL reason={StartupConfigError}");
            }
            Console.WriteLine("[StopLatch] Ready");
        }

        private static string ValidateStartupConfig()
        {
            string configPath = AppDomain.CurrentDomain.SetupInformation.ConfigurationFile;
            if (!File.Exists(configPath))
            {
                return $"config missing: {configPath}";
            }

            string[] requiredKeys = new[]
            {
                "X_MIN", "X_MAX", "Y_MIN", "Y_MAX", "Z_MIN", "Z_MAX"
            };

            foreach (string key in requiredKeys)
            {
                if (!AppSettings.TryGetValue(key, out string rawValue))
                {
                    return $"missing appSetting: {key}";
                }

                if (!double.TryParse(rawValue, NumberStyles.Float, CultureInfo.InvariantCulture, out double parsed) ||
                    !IsFinite(parsed))
                {
                    return $"invalid pose bound: {key}";
                }
            }

            if (!(XMin < XMax && YMin < YMax && ZMin < ZMax))
            {
                return "invalid pose bounds ordering";
            }

            return string.Empty;
        }

        private void ApplyStartupConfigSafety()
        {
            if (string.IsNullOrWhiteSpace(StartupConfigError))
            {
                return;
            }

            Interlocked.Exchange(ref StopLatch, 1);
            UpdateStatusLatchUi(true);
            UpdateStateLabel("CONFIG_ERROR");
            Console.WriteLine($"[Config] FAIL-CLOSED: {StartupConfigError}");
        }

        public static bool IsRuntimeConfigValid()
        {
            return string.IsNullOrWhiteSpace(StartupConfigError);
        }

        public static bool CanTransmitRobotPoses()
        {
            return IsRuntimeConfigValid() && Volatile.Read(ref StopLatch) == 0;
        }

        public static string GetRobotSendBlockReason()
        {
            if (!IsRuntimeConfigValid())
            {
                return StartupConfigError;
            }

            return Volatile.Read(ref StopLatch) == 1 ? "StopLatch active" : string.Empty;
        }

        private GapResult EvaluateGap(int poseCount)
        {
            if (poseCount <= 0)
            {
                return new GapResult { Result = "NG", MaxGap = 0, AvgGap = 0, RmsGap = 0, Reason = "NO_POSE" };
            }

            if (TryReadGapMetrics(out GapMetricsSnapshot metrics, out string loadReason))
            {
                string result;
                string reason;

                if (metrics.MaxGap > MaxTol)
                {
                    result = "NG";
                    reason = "GAP_EXCEED_MAX";
                }
                else if (metrics.AvgGap > AvgTol)
                {
                    result = "NG";
                    reason = "GAP_EXCEED_AVG";
                }
                else
                {
                    result = "OK";
                    reason = "WITHIN_TOL";
                }

                if (result == "OK" && IcpQualityEnforce)
                {
                    if (!metrics.IcpFitness.HasValue || !metrics.IcpInlierRmse.HasValue)
                    {
                        result = "NG";
                        reason = "ICP_METRIC_MISSING";
                    }
                    else if (metrics.IcpFitness.Value < IcpFitnessMin)
                    {
                        result = "NG";
                        reason = "ICP_FITNESS_LOW";
                    }
                    else if (metrics.IcpInlierRmse.Value > IcpInlierRmseMax)
                    {
                        result = "NG";
                        reason = "ICP_RMSE_HIGH";
                    }
                }

                return new GapResult
                {
                    Result = result,
                    MaxGap = metrics.MaxGap,
                    AvgGap = metrics.AvgGap,
                    RmsGap = metrics.RmsGap,
                    Reason = reason
                };
            }

            if (GapAllowLegacyRandom)
            {
                GapResult legacy = EvaluateGapLegacy(poseCount);
                legacy.Reason = $"LEGACY_{legacy.Reason}";
                return legacy;
            }

            return new GapResult
            {
                Result = "NG",
                MaxGap = 0,
                AvgGap = 0,
                RmsGap = 0,
                Reason = string.IsNullOrWhiteSpace(loadReason) ? "NO_RESULT" : loadReason
            };
        }

        private GapResult EvaluateGapLegacy(int poseCount)
        {
            List<double> gaps = new List<double>(poseCount);
            for (int i = 0; i < poseCount; i++)
            {
                double gap = (GapMode == "uniform") ? AvgTol * 0.5 : GapRandom.NextDouble() * (MaxTol * 1.5);
                gaps.Add(gap);
            }

            double maxGap = gaps.Max();
            double avgGap = gaps.Average();
            double rmsGap = Math.Sqrt(gaps.Select(g => g * g).Average());
            string result;
            string reason;

            if (maxGap > MaxTol)
            {
                result = "NG";
                reason = "GAP_EXCEED_MAX";
            }
            else if (avgGap > AvgTol)
            {
                result = "NG";
                reason = "GAP_EXCEED_AVG";
            }
            else
            {
                result = "OK";
                reason = "WITHIN_TOL";
            }

            return new GapResult { Result = result, MaxGap = maxGap, AvgGap = avgGap, RmsGap = rmsGap, Reason = reason };
        }

        private static string ResolveGapJsonPath()
        {
            if (Path.IsPathRooted(GapJsonPathSetting))
            {
                return GapJsonPathSetting;
            }

            return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, GapJsonPathSetting);
        }

        private bool TryReadGapMetrics(out GapMetricsSnapshot snapshot, out string reason)
        {
            snapshot = default(GapMetricsSnapshot);
            reason = "NO_RESULT";

            string path = ResolveGapJsonPath();
            if (!File.Exists(path))
            {
                return false;
            }

            try
            {
                using (FileStream fs = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    var serializer = new DataContractJsonSerializer(typeof(GapInputRoot));
                    GapInputRoot root = serializer.ReadObject(fs) as GapInputRoot;
                    if (root == null || root.metrics == null)
                    {
                        reason = "INVALID_GAP_DATA";
                        return false;
                    }

                    if (root.metrics.samples <= 0)
                    {
                        reason = "NO_RESULT";
                        return false;
                    }

                    double maxGap = root.metrics.max_gap_mm;
                    double avgGap = root.metrics.avg_gap_mm;
                    double rmsGap = root.metrics.rms_gap_mm;
                    if (!IsFinite(maxGap) || !IsFinite(avgGap) || !IsFinite(rmsGap))
                    {
                        reason = "INVALID_GAP_DATA";
                        return false;
                    }

                    if (!string.IsNullOrWhiteSpace(root.timestamp))
                    {
                        if (!DateTime.TryParse(root.timestamp, CultureInfo.InvariantCulture, DateTimeStyles.AssumeLocal, out DateTime ts))
                        {
                            reason = "INVALID_GAP_DATA";
                            return false;
                        }

                        if (GapMaxAgeMs > 0)
                        {
                            TimeSpan age = DateTime.Now - ts;
                            if (age.TotalMilliseconds > GapMaxAgeMs)
                            {
                                reason = "STALE_GAP_DATA";
                                return false;
                            }
                        }
                    }

                    snapshot = new GapMetricsSnapshot
                    {
                        MaxGap = maxGap,
                        AvgGap = avgGap,
                        RmsGap = rmsGap,
                        Samples = root.metrics.samples,
                        IcpFitness = root.metrics.icp_fitness ?? root.quality?.icp_fitness,
                        IcpInlierRmse = root.metrics.icp_inlier_rmse ?? root.quality?.icp_inlier_rmse
                    };

                    if (snapshot.IcpFitness.HasValue && !IsFinite(snapshot.IcpFitness.Value))
                    {
                        reason = "INVALID_GAP_DATA";
                        return false;
                    }
                    if (snapshot.IcpInlierRmse.HasValue && !IsFinite(snapshot.IcpInlierRmse.Value))
                    {
                        reason = "INVALID_GAP_DATA";
                        return false;
                    }

                    reason = "WITHIN_TOL";
                    return true;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[Gap] read error: {ex.Message}");
                reason = "INVALID_GAP_DATA";
                return false;
            }
        }

        private static bool IsFinite(double value)
        {
            return !(double.IsNaN(value) || double.IsInfinity(value));
        }

        private struct GapResult
        {
            public string Result;
            public double MaxGap;
            public double AvgGap;
            public double RmsGap;
            public string Reason;
        }

        private struct GapMetricsSnapshot
        {
            public double MaxGap;
            public double AvgGap;
            public double RmsGap;
            public int Samples;
            public double? IcpFitness;
            public double? IcpInlierRmse;
        }

        [DataContract]
        private class GapInputRoot
        {
            [DataMember]
            public string session_id { get; set; }

            [DataMember]
            public string part_id { get; set; }

            [DataMember]
            public string timestamp { get; set; }

            [DataMember]
            public GapInputMetrics metrics { get; set; }

            [DataMember]
            public GapInputQuality quality { get; set; }
        }

        [DataContract]
        private class GapInputMetrics
        {
            [DataMember]
            public double max_gap_mm { get; set; }

            [DataMember]
            public double avg_gap_mm { get; set; }

            [DataMember]
            public double rms_gap_mm { get; set; }

            [DataMember]
            public int samples { get; set; }

            [DataMember]
            public double? icp_fitness { get; set; }

            [DataMember]
            public double? icp_inlier_rmse { get; set; }
        }

        [DataContract]
        private class GapInputQuality
        {
            [DataMember]
            public double? icp_fitness { get; set; }

            [DataMember]
            public double? icp_inlier_rmse { get; set; }
        }

        private void btn_Status_Click(object sender, EventArgs e)
        {
            if (!IsRuntimeConfigValid())
            {
                Console.WriteLine($"[StopLatch] Reset blocked: invalid config ({StartupConfigError})");
                UpdateStateLabel("CONFIG_ERROR");
                return;
            }
            Interlocked.Exchange(ref StopLatch, 0);
            ResetStatusCache();
            UpdateStatusLatchUi(false);
            Console.WriteLine("[StopLatch] Reset by UI.");
            UpdateStateLabel("RESET");
        }

        private void UpdateStatusLatchUi(bool latched)
        {
            if (btn_Status.InvokeRequired)
            {
                btn_Status.Invoke(new Action<bool>(UpdateStatusLatchUi), latched);
                return;
            }

            if (latched)
            {
                btn_Status.Text = "STOP";
                btn_Status.BackColor = Color.DarkRed;
            }
            else
            {
                btn_Status.Text = "FINISH";
                btn_Status.BackColor = Color.Maroon;
            }
        }

        private void UpdateConfigLabel()
        {
            if (lbl_Config.InvokeRequired)
            {
                lbl_Config.Invoke(new Action(UpdateConfigLabel));
                return;
            }

            string pad = PadLastPacket ? "1" : "0";
            lbl_Config.Text = $"CFG: POSE={PosesPerPacket} PAD={pad} CNT={CntFieldMode} GAP={GapMode}";
        }

        private void UpdateStateLabel(string state)
        {
            if (lbl_State.InvokeRequired)
            {
                lbl_State.Invoke(new Action<string>(UpdateStateLabel), state);
                return;
            }

            lbl_State.Text = $"STATE: {state}";
        }

        private void UpdateLastNgLabel(GapResult gapResult)
        {
            if (lbl_LastNg.InvokeRequired)
            {
                lbl_LastNg.Invoke(new Action<GapResult>(UpdateLastNgLabel), gapResult);
                return;
            }

            lbl_LastNg.Text = $"Last NG: {gapResult.Reason} max={gapResult.MaxGap:F3} avg={gapResult.AvgGap:F3} rms={gapResult.RmsGap:F3}";
        }

        private List<string> BuildPlannedPayloads(List<Pose> poses)
        {
            List<string> payloads = new List<string>();
            for (int i = 0; i < poses.Count; i += PosesPerPacket)
            {
                var batch = poses.GetRange(i, Math.Min(PosesPerPacket, poses.Count - i));

                if (PadLastPacket && batch.Count < PosesPerPacket && batch.Count > 0)
                {
                    Pose last = batch[batch.Count - 1];
                    while (batch.Count < PosesPerPacket)
                    {
                        batch.Add(last);
                    }
                }

                int cntForHeader = (CntFieldMode == "total") ? poses.Count : batch.Count;
                payloads.Add(BuildPayload(batch, cntForHeader));
            }
            return payloads;
        }

        private static void EnsureLogDir(out string dayDir)
        {
            string day = DateTime.Now.ToString("yyyy-MM-dd");
            dayDir = Path.Combine(LogRoot, day);
            Directory.CreateDirectory(dayDir);
        }

        private void WriteOkLog(GapResult gapResult)
        {
            EnsureLogDir(out string dayDir);
            string okPath = Path.Combine(dayDir, "ok.log");
            string line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss}\tsession={SessionId}\tresult={gapResult.Result}\tmax={gapResult.MaxGap:F3}\tavg={gapResult.AvgGap:F3}\trms={gapResult.RmsGap:F3}\treason={gapResult.Reason}\n";
            File.AppendAllText(okPath, line);
        }

        private void WriteNgLog(GapResult gapResult, List<string> payloads)
        {
            EnsureLogDir(out string dayDir);
            string fileName = $"NG_{DateTime.Now:yyyyMMdd_HHmmss}_{SessionId}.json";
            string path = Path.Combine(dayDir, fileName);

            var sb = new StringBuilder();
            sb.Append("{");
            sb.Append($"\"timestamp\":\"{DateTime.Now:yyyy-MM-dd HH:mm:ss}\",");
            sb.Append($"\"session_id\":\"{SessionId}\",");
            sb.Append("\"config\":{");
            sb.Append($"\"POSES_PER_PACKET\":{PosesPerPacket},");
            sb.Append($"\"PAD_LAST_PACKET\":{PadLastPacket.ToString().ToLowerInvariant()},");
            sb.Append($"\"CNT_FIELD_MODE\":\"{CntFieldMode}\",");
            sb.Append($"\"MAX_TOL\":{MaxTol.ToString("F3", CultureInfo.InvariantCulture)},");
            sb.Append($"\"AVG_TOL\":{AvgTol.ToString("F3", CultureInfo.InvariantCulture)},");
            sb.Append($"\"GAP_MODE\":\"{GapMode}\"");
            sb.Append("},");
            sb.Append($"\"ready_message\":\"{EscapeJson(LastRobotMessage)}\",");
            sb.Append("\"planned_payloads\":[");
            for (int i = 0; i < payloads.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.Append($"\"{EscapeJson(payloads[i])}\"");
            }
            sb.Append("],");
            sb.Append("\"decision\":{");
            sb.Append($"\"result\":\"{gapResult.Result}\",");
            sb.Append($"\"max_gap\":{gapResult.MaxGap.ToString("F3", CultureInfo.InvariantCulture)},");
            sb.Append($"\"avg_gap\":{gapResult.AvgGap.ToString("F3", CultureInfo.InvariantCulture)},");
            sb.Append($"\"rms_gap\":{gapResult.RmsGap.ToString("F3", CultureInfo.InvariantCulture)},");
            sb.Append($"\"reason\":\"{gapResult.Reason}\",");
            sb.Append($"\"send_blocked\":true,");
            bool stopLatchNow = Volatile.Read(ref StopLatch) == 1;
            sb.Append($"\"stop_latch\":{stopLatchNow.ToString().ToLowerInvariant()}");
            sb.Append("}");
            sb.Append("}");

            File.WriteAllText(path, sb.ToString());
        }

        private static string EscapeJson(string value)
        {
            if (value == null) return "";
            return value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n");
        }

        private void SendStatusOnce(string code, string reason, double? maxGap, double? avgGap)
        {
            if (!StatusEnable)
            {
                return;
            }

            string ts = DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss.fff", CultureInfo.InvariantCulture);
            string key = $"{code}|{reason}";
            long nowMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            long elapsed = nowMs - LastStatusSentAtMs;
            long remaining = StatusCooldownMs > 0 ? Math.Max(0, StatusCooldownMs - elapsed) : 0;

            bool sameKey = key == LastStatusKey;
            bool stopLatchNow = Volatile.Read(ref StopLatch) == 1;
            bool latchedBlock = stopLatchNow && !StatusResendWhileLatched && string.Equals(reason, "LATCHED", StringComparison.OrdinalIgnoreCase);
            bool canSendByChange = StatusSendOnStateChange && !sameKey;
            bool canSendByCooldown = StatusCooldownMs <= 0 ? !sameKey : elapsed >= StatusCooldownMs;
            bool shouldSend = (canSendByChange || canSendByCooldown) && !latchedBlock;

            if (!shouldSend)
            {
                Console.WriteLine($"[Status] suppressed key={key} cooldown_remaining_ms={remaining}");
                return;
            }
            LastStatusKey = key;
            LastStatusSentAtMs = nowMs;

            StringBuilder sb = new StringBuilder();
            sb.Append(code);
            sb.Append(",");
            sb.Append(reason ?? "NA");
            if (maxGap.HasValue && avgGap.HasValue)
            {
                sb.Append(",");
                sb.Append(maxGap.Value.ToString("F3", CultureInfo.InvariantCulture));
                sb.Append(",");
                sb.Append(avgGap.Value.ToString("F3", CultureInfo.InvariantCulture));
            }
            sb.Append(",");
            sb.Append(ts);

            SendStatusUdp(sb.ToString());
            Console.WriteLine($"[Status] {sb} status_sent=true");
        }

        private static void ResetStatusCache()
        {
            LastStatusKey = string.Empty;
            LastStatusSentAtMs = 0;
        }

        private void SendStatusUdp(string message)
        {
            try
            {
                using (UdpClient client = new UdpClient())
                {
                    byte[] data = Encoding.ASCII.GetBytes(message);
                    client.Send(data, data.Length, StatusTargetIp, StatusPort);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[Status] UDP send error: {ex.Message}");
            }
        }

        private bool IsPoseInRange(Pose p)
        {
            return p.X >= XMin && p.X <= XMax &&
                   p.Y >= YMin && p.Y <= YMax &&
                   p.Z >= ZMin && p.Z <= ZMax;
        }

        private void TriggerSafetyLatch(string reason, string logMessage)
        {
            Interlocked.Exchange(ref StopLatch, 1);
            UpdateStatusLatchUi(true);
            Console.WriteLine(logMessage);
            // Force immediate emission of the critical latch reason regardless of prior cooldown state.
            ResetStatusCache();
            SendStatusOnce("2002", reason, null, null);
            UpdateStateLabel("LATCHED");
        }

        public struct Pose
        {
            public double X, Y, Z, Rx, Ry, Rz;
            public Pose(double x, double y, double z, double rx, double ry, double rz)
            {
                X = x; Y = y; Z = z;
                Rx = rx; Ry = ry; Rz = rz;
            }
        }
    }
}
