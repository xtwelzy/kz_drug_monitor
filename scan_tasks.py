# scan_tasks.py
import queue

# Очередь задач на ручное сканирование.
# В неё будет класть задачи веб-интерфейс, а основной монитор забирать.
scan_queue: queue.Queue[str] = queue.Queue()
