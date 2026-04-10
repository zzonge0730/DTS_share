using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace DTS
{
    static class Program
    {
        /// <summary>
        /// 해당 애플리케이션의 주 진입점입니다.
        /// </summary>
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new Form1());
        }
    }
}
namespace DTS
{
    static class ProtocolPreprocessor
    {
        public static string Preprocessing(string data)
        {
            string[] commands = data.Split(','); // ',' 기준으로 토큰화
            StringBuilder sb = new StringBuilder(); // 하나의 string으로 합치기
            sb.Append(commands[0]); // 상태코드
            sb.Append(',');
            sb.Append(commands[1]); // 포즈 수
            sb.Append(',');

            for (int i = 2; i < commands.Length; i++)
            {
                if (!commands[i].Contains("."))
                {
                    commands[i] += ".";
                }

                if (commands[i].Length < 7)
                {
                    commands[i] = commands[i].PadRight(7, '0');
                }
                else if (commands[i].Length > 7)
                {
                    commands[i] = commands[i].Substring(0, 7);
                }

                sb.Append(commands[i]);

                if (i < commands.Length - 1)
                {
                    sb.Append(',');
                }
            }

            return sb.ToString();
        }
    }
}
