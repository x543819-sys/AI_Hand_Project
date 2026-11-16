import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0)

# 强制置顶窗口
cv2.namedWindow("AI Gesture Recognition", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("AI Gesture Recognition", cv2.WND_PROP_TOPMOST, 1)

# 获取各个手指指尖的ID
tipIds = [4, 8, 12, 16, 20] 

while True:
    success, img = cap.read()
    if not success: break
    
    img = cv2.flip(img, 1)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)
    
    lmList = []
    if results.multi_hand_landmarks:
        for handLms in results.multi_hand_landmarks:
            # 1. 提取所有点的坐标存入列表 (id, x, y)
            for id, lm in enumerate(handLms.landmark):
                h, w, c = img.shape
                cx, cy = int(lm.x * w), int(lm.y * h)
                lmList.append([id, cx, cy])
            
            mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS)

    # 2. 如果检测到了手，开始判断手指状态
    if len(lmList) != 0:
        fingers = []
        
                # 用距离法判断大拇指（不受正反面和左右手影响）
        x4, y4 = lmList[4][1], lmList[4][2]
        x3, y3 = lmList[3][1], lmList[3][2]
        x17, y17 = lmList[17][1], lmList[17][2]

        # 计算指尖到17号点的距离
        dist_tip = ((x4 - x17)**2 + (y4 - y17)**2)**0.5
        # 计算关节到17号点的距离
        dist_joint = ((x3 - x17)**2 + (y3 - y17)**2)**0.5

        if dist_tip > dist_joint:
            fingers.append(1) # 指尖更远，说明伸开了
        else:
            fingers.append(0)
            
        # 其他四根手指（比较上下，指尖y小于关节y说明是伸开的）
        for id in range(1, 5):
            if lmList[tipIds[id]][2] < lmList[tipIds[id] - 2][2]:
                fingers.append(1)
            else:
                fingers.append(0)
                
        # 3. 根据伸出的手指数量，判断手势
        totalFingers = fingers.count(1)
        
        gesture = "Unknown"
        if totalFingers == 0:
            gesture = "Rock (石头)"
        elif totalFingers == 5:
            gesture = "Paper (布)"
        elif totalFingers == 2 and fingers[1] == 1 and fingers[2] == 1:
            gesture = "Scissors (剪刀)"
        
        # 4. 在屏幕上打上文字
        cv2.rectangle(img, (20, 300), (250, 425), (0, 255, 0), cv2.FILLED)
        cv2.putText(img, gesture, (30, 390), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
            
    cv2.imshow("AI Gesture Recognition", img)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()