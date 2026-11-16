import cv2

# 1. 启动默认摄像头（通常是0）
cap = cv2.VideoCapture(0)

while True:
    # 2. 读取每一帧画面
    success, img = cap.read()
    if not success:
        print("摄像头打不开！检查一下有没有被其他软件占用")
        break
        
    # 3. 翻转画面（像照镜子一样，符合直觉）
    img = cv2.flip(img, 1)
    
    # 4. 显示画面
    cv2.imshow("My First AI Project", img)
    
    # 5. 按下 'q' 键退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放资源
cap.release()
cv2.destroyAllWindows()