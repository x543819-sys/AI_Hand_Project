import cv2
import mediapipe as mp
import numpy as np # 需要引入 numpy 来做坐标映射

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0)
cv2.namedWindow("Air Mouse", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("Air Mouse", cv2.WND_PROP_TOPMOST, 1)

while True:
    success, img = cap.read()
    if not success: break
    
    # 获取画面的宽和高
    h, w, c = img.shape
    
    img = cv2.flip(img, 1)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)
    
    # 创建一个黑色的虚拟画布（用来展示光标移动）
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    
    if results.multi_hand_landmarks:
        for handLms in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS)
            
            # 提取食指指尖（8号点）的坐标
            lm = handLms.landmark[8]
            # 因为 lm.x 和 lm.y 是 0 到 1 的比例，我们需要乘上画面的宽高
            cx, cy = int(lm.x * w), int(lm.y * h)
            
            # 在真实画面上标出指尖
            cv2.circle(img, (cx, cy), 15, (0, 255, 0), cv2.FILLED)
            
            # 在黑画布上，根据指尖位置画一个红色的小球（模拟光标）
            cv2.circle(canvas, (cx, cy), 30, (0, 0, 255), cv2.FILLED)
            
            # 在黑画布上写上坐标
            cv2.putText(canvas, f"X:{cx} Y:{cy}", (cx + 40, cy), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    # 把真实画面和虚拟画布拼在一起显示
    combined = np.hstack((img, canvas))
    
    # 缩小一点显示，因为两个画面拼一起太宽了
    combined_small = cv2.resize(combined, (int(w * 1.2), int(h * 0.6)))
    
    cv2.imshow("Air Mouse", combined_small)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()