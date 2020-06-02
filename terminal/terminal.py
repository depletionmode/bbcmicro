#!/usr/bin/env python3

from serial import Serial
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtDBus import *

import signal
signal.signal(signal.SIGINT, signal.SIG_DFL) #

class CommandHistory(QObject):
    selected = pyqtSignal(object)
    
    def __init__(self):
        QObject.__init__(self)

        self.index = 0
        self.working_buf = []
        self.history = [[]]

    def scrollUp(self):
        # only scroll if not in record mode
        if len(self.working_buf) > 0:
            return
            
        if len(self.history) > self.index + 1:
            self.index += 1
            self.emit()
        
    def scrollDown(self):
        # only scroll if not in record mode
        if len(self.working_buf) > 0:
            return

        if self.index - 1 > -1:
            self.index -= 1
            self.emit()

    def scrollReset(self):
        self.index = 0
        self.emit()

    def getSelected(self):
        return self.history[self.index]

    def recordChar(self, c):
        # only record if not in scroll mode
        if self.index == 0:
            self.working_buf.append(c)

    def flush(self):
        if len(self.working_buf) > 0:
            self.history.insert(1, self.working_buf)
            self.working_buf = []

        self.scrollReset()

    def emit(self):
        self.selected.emit(self.history[self.index])


class BbcMicroMode7TextEdit(QTextEdit):
    def __init__(self, *args):
        QTextEdit.__init__(self, *args)

        self.font = QFont()
        self.font.setFamily("ModeSeven")
        self.font.setFixedPitch(True)
        self.font.setPointSize(25)
        self.setFont(self.font)

        p = self.palette()
        p.setColor(QPalette.Base, Qt.black)
        p.setColor(QPalette.Text, Qt.white)
        self.setPalette(p)

        self.setLineWrapMode(QTextEdit.FixedColumnWidth)
        self.setLineWrapColumnOrWidth(40)

        self.setUndoRedoEnabled(False)

        self.history = CommandHistory()

    def setTextSize(self, point_size):
        self.font.setPointSize(point_size)

    def installCharConsumer(self, obj):
        self.charConsumer = obj.charConsumer
    
    def insertChar(self, c):
        c = ord(c)
        print(c)
        alpha_numeric = range(20, 126)
        delete_key = 127

        text_color_control_codes = {
            129 : Qt.red,
            130 : Qt.green,
            131 : Qt.yellow,
            132 : Qt.blue,
            133 : Qt.magenta,
            134 : Qt.cyan,
            135 : Qt.white
        }

        color = text_color_control_codes.get(c)
        if color:
            self.setTextColor(color)
            print("change color to {}".format(c))
            return

        if c in alpha_numeric:
            self.insertPlainText(chr(c))
            self.moveCursor(QTextCursor.End)
            return

        if c == 10:
            self.setTextColor(Qt.white)
            return

        if c == 13:
            self.append('')
            return

        if c == delete_key:
            self.textCursor().deletePreviousChar()
            
        #print('Unhandled char: {}'.format(c))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Return:
            history = self.history.getSelected()
            for c in history:
                self.charConsumer(c)

            self.charConsumer(ord('\r'))
            #self.charConsumer(ord('\n'))

            self.history.flush()

        elif e.key() == Qt.Key_Up:
            self.history.scrollUp()
        elif e.key() == Qt.Key_Down:
            self.history.scrollDown()
        elif e.key() == Qt.Key_Delete:
            self.charConsumer(127)
        else:
            self.charConsumer(e.key())
            self.history.recordChar(e.key())

    def getHistorySignal(self):
        return self.history.selected

class SerialReadThread(QThread):
    char_received = pyqtSignal(object)
    
    def __init__(self, ser, ins):
        QThread.__init__(self)

        self.ser = ser

    def run(self):
        while True:
            c = self.ser.read(1)
            self.char_received.emit(c)

class QDBusServer(QObject):
    Q_CLASSINFO("D-Bus Interface", "org.bbcmicro.terminal")
    Q_CLASSINFO("D-Bus Introspection",
    '  <interface name="org.bbcmicro.terminal">\n'
    '    <method name="cmd">\n'
    '      <arg direction="in" type="s" name="cmd"/>\n'
    '    </method>\n'
    '  </interface>\n')

    def __init__(self, cmd_fcn):
        QObject.__init__(self)

        self.cmd_fcn = cmd_fcn

    @pyqtSlot(str, result=str)
    def cmd(self, cmd):
        for c in cmd:
            c = ord(c)
            print(c)
            self.cmd_fcn(c)
        self.cmd_fcn(ord('\r'))

class MainWindow(QMainWindow):
    def __init__(self, ser):
        QMainWindow.__init__(self)

        self.ser = ser

        self.text = BbcMicroMode7TextEdit(self)
        self.text.installCharConsumer(self)
        self.text.getHistorySignal().connect(self.onHistorySelected)

        self.setCentralWidget(self.text)
        #self.setFixedSize(800,600)

        self.historyLabel = QLabel(self)
        self.historyLabel.show()

        #self.dbus_conn = QDBusConnection.connectToBus('tcp:host=localhost, port=54354', 'bbcmicroTerminalBus')
        #self.dbus_inf = QDBusInterface('org.bbcmicro.terminal', '/org/bbcmicro/terminal', '')

        self.dbus_srv = QDBusServer(self.charConsumer)
        self.dbus_bus = QDBusConnection.systemBus()
        print(self.dbus_bus.registerObject('/', self.dbus_srv, QDBusConnection.ExportAllSlots))
        print(self.dbus_bus.registerService('org.bbcmicro.terminal'))

    def loop(self):
        self.threads = []
        reader = SerialReadThread(ser, self.text.insertChar)
        reader.char_received.connect(self.onCharReady)
        self.threads.append(reader)
        reader.start()

    def onCharReady(self, c):
        self.text.insertChar(c)

    def onHistorySelected(self, h):
        if len(h) == 0:
            self.statusBar().hide()
        else:
            self.statusBar().showMessage(''.join([chr(c) for c in h]))
            self.statusBar().show()

    def charConsumer(self, c):
        b = bytearray(1)
        b[0] = c
        ser.write(b)

ser = Serial('/dev/ttyUSB0', 9600)

app = QApplication([])
app.setApplicationName("BBC Micro Terminal")

window = MainWindow(ser)
window.show()
window.loop()

app.exec_()
