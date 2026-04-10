
namespace DTS
{
    partial class Form1
    {
        /// <summary>
        /// 필수 디자이너 변수입니다.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// 사용 중인 모든 리소스를 정리합니다.
        /// </summary>
        /// <param name="disposing">관리되는 리소스를 삭제해야 하면 true이고, 그렇지 않으면 false입니다.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form 디자이너에서 생성한 코드

        /// <summary>
        /// 디자이너 지원에 필요한 메서드입니다. 
        /// 이 메서드의 내용을 코드 편집기로 수정하지 마세요.
        /// </summary>
        private void InitializeComponent()
        {
            this.btn_Con_Robot = new System.Windows.Forms.Button();
            this.btn_Send_Pose = new System.Windows.Forms.Button();
            this.btn_Con_Vision = new System.Windows.Forms.Button();
            this.btn_Status = new System.Windows.Forms.Button();
            this.lbl_State = new System.Windows.Forms.Label();
            this.lbl_Config = new System.Windows.Forms.Label();
            this.lbl_LastNg = new System.Windows.Forms.Label();
            this.SuspendLayout();
            // 
            // btn_Con_Robot
            // 
            this.btn_Con_Robot.Font = new System.Drawing.Font("굴림", 9F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(129)));
            this.btn_Con_Robot.Location = new System.Drawing.Point(12, 96);
            this.btn_Con_Robot.Name = "btn_Con_Robot";
            this.btn_Con_Robot.Size = new System.Drawing.Size(153, 36);
            this.btn_Con_Robot.TabIndex = 0;
            this.btn_Con_Robot.Text = "Connect_Robot";
            this.btn_Con_Robot.UseVisualStyleBackColor = true;
            this.btn_Con_Robot.Click += new System.EventHandler(this.btn_Con_Robot_Click);
            // 
            // btn_Send_Pose
            // 
            this.btn_Send_Pose.Font = new System.Drawing.Font("굴림", 9F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(129)));
            this.btn_Send_Pose.Location = new System.Drawing.Point(12, 147);
            this.btn_Send_Pose.Name = "btn_Send_Pose";
            this.btn_Send_Pose.Size = new System.Drawing.Size(153, 36);
            this.btn_Send_Pose.TabIndex = 1;
            this.btn_Send_Pose.Text = "Disconnect";
            this.btn_Send_Pose.UseVisualStyleBackColor = true;
            this.btn_Send_Pose.Click += new System.EventHandler(this.btn_Send_Pose_Click);
            // 
            // btn_Con_Vision
            // 
            this.btn_Con_Vision.Font = new System.Drawing.Font("굴림", 9F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(129)));
            this.btn_Con_Vision.Location = new System.Drawing.Point(12, 44);
            this.btn_Con_Vision.Name = "btn_Con_Vision";
            this.btn_Con_Vision.Size = new System.Drawing.Size(153, 36);
            this.btn_Con_Vision.TabIndex = 2;
            this.btn_Con_Vision.Text = "Connect_Vision";
            this.btn_Con_Vision.UseVisualStyleBackColor = true;
            this.btn_Con_Vision.Click += new System.EventHandler(this.btn_Con_Vision_Click);
            // 
            // btn_Status
            // 
            this.btn_Status.BackColor = System.Drawing.Color.Maroon;
            this.btn_Status.Font = new System.Drawing.Font("굴림", 18F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(129)));
            this.btn_Status.ForeColor = System.Drawing.SystemColors.ButtonHighlight;
            this.btn_Status.Location = new System.Drawing.Point(214, 44);
            this.btn_Status.Name = "btn_Status";
            this.btn_Status.Size = new System.Drawing.Size(180, 139);
            this.btn_Status.TabIndex = 3;
            this.btn_Status.Text = "FINISH";
            this.btn_Status.UseVisualStyleBackColor = false;
            this.btn_Status.Click += new System.EventHandler(this.btn_Status_Click);
            // 
            // lbl_State
            // 
            this.lbl_State.AutoSize = true;
            this.lbl_State.Font = new System.Drawing.Font("굴림", 9F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(129)));
            this.lbl_State.Location = new System.Drawing.Point(214, 16);
            this.lbl_State.Name = "lbl_State";
            this.lbl_State.Size = new System.Drawing.Size(141, 12);
            this.lbl_State.TabIndex = 4;
            this.lbl_State.Text = "STATE: DISCONNECTED";
            // 
            // lbl_Config
            // 
            this.lbl_Config.AutoSize = true;
            this.lbl_Config.Font = new System.Drawing.Font("굴림", 8F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(129)));
            this.lbl_Config.Location = new System.Drawing.Point(12, 196);
            this.lbl_Config.Name = "lbl_Config";
            this.lbl_Config.Size = new System.Drawing.Size(128, 11);
            this.lbl_Config.TabIndex = 5;
            this.lbl_Config.Text = "CFG: POSE=3 PAD=1";
            // 
            // lbl_LastNg
            // 
            this.lbl_LastNg.AutoSize = true;
            this.lbl_LastNg.Font = new System.Drawing.Font("굴림", 8F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(129)));
            this.lbl_LastNg.Location = new System.Drawing.Point(12, 216);
            this.lbl_LastNg.Name = "lbl_LastNg";
            this.lbl_LastNg.Size = new System.Drawing.Size(99, 11);
            this.lbl_LastNg.TabIndex = 6;
            this.lbl_LastNg.Text = "Last NG: (none)";
            // 
            // Form1
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(7F, 12F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(406, 250);
            this.Controls.Add(this.lbl_LastNg);
            this.Controls.Add(this.lbl_Config);
            this.Controls.Add(this.lbl_State);
            this.Controls.Add(this.btn_Status);
            this.Controls.Add(this.btn_Con_Vision);
            this.Controls.Add(this.btn_Send_Pose);
            this.Controls.Add(this.btn_Con_Robot);
            this.Name = "Form1";
            this.Text = "Form1";
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.Button btn_Con_Robot;
        private System.Windows.Forms.Button btn_Send_Pose;
        private System.Windows.Forms.Button btn_Con_Vision;
        private System.Windows.Forms.Button btn_Status;
        private System.Windows.Forms.Label lbl_State;
        private System.Windows.Forms.Label lbl_Config;
        private System.Windows.Forms.Label lbl_LastNg;
    }
}

