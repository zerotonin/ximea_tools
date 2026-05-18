import cv2
from ximea import xiapi
import multiprocessing as mp
from datetime import datetime, timedelta



class mp4Writer():
    """[summary]
    """    


    def __init__(self, fPos, fps, frameShape, grayFlag=True):
        """[summary]

        Args:
            fPos ([type]): [description]
            fps ([type]): [description]
            frameShape ([type]): [description]
            grayFlag (bool, optional): [description]. Defaults to True.
        """        
        self.fPos = fPos
        self.fps = fps
        self.frameShape = frameShape
        self.grayFlag = grayFlag
        # Define the codec and create VideoWriter object             
        fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')             
        self.out = cv2.VideoWriter(fPos, fourcc, fps, frameShape) 


    def colormanipulation(self, frame):
        print('frame:', type(frame))
        return cv2.merge([frame, frame, frame])                 


    def write(self, frame):
        if self.grayFlag:
            self.out.write(self.colormanipulation(frame))
        else:
            self.out.write(frame)   


    def close(self):
        self.out.release()



class xiCamControl():


    def __init__(self, exposure, fps, roiOffset=False, roiSize=False):
        # create instance for first connected camera
        self.cam = xiapi.Camera()
        # start communication
        self.cam.open_device()
        # set exposure in µs
        self.exposure = exposure
        self.setEXP()
        # set framerate
        self.fps = fps
        self.setFPS()
        # set roi
        self.roiSize = roiSize
        self.roiOffset = roiOffset
        self.setROI()
        # create instance of Image to store image data and metadata
        self.img = xiapi.Image()
        self.testInit()


    def testInit(self):
        try:
            self.startACQ()
            self.currentFrame = self.getImage()
            self.stopACQ()
            print ('Camera test successful!\n')    
        except: 
            raise ValueError('Could not initialise camera')


    def setEXP(self):
        self.cam.set_exposure(self.exposure)


    def setFPS(self):
        self.cam.set_acq_timing_mode('XI_ACQ_TIMING_MODE_FRAME_RATE')
        self.cam.set_framerate(self.fps)


    def setROI(self):
        if type(self.roiOffset) == tuple and type(self.roiSize) == tuple:
            self.cam.set_width(self.roiSize[0])
            self.cam.set_height(self.roiSize[1])
            self.cam.set_offsetX(self.roiOffset[0])        
            self.cam.set_offsetY(self.roiOffset[1])


    def getImage(self):
        self.cam.get_image(self.img)
        self.currentFrame = self.img.get_image_data_numpy()
        print('currentFrame:', type(self.currentFrame))
        return self.currentFrame


    def startACQ(self):
        # start data acquisition
        self.cam.start_acquisition()
    

    def stopACQ(self):
        # stop data acquisition
        self.cam.stop_acquisition()


    def close(self):
        # stop communication
        self.cam.close_device()



class xiRecorder():


    def __init__(self, exposure, fps, frameShape, roiOffset=False, durationSEC=10, grayFlag=True):
        # initiate xiCamControl
        self.xiCam = xiCamControl(exposure, fps, roiOffset=roiOffset, roiSize=frameShape)
        # automatically set file anme to yyyy-mm-dd_hh-mm-ss
        self.now = datetime.now()
        self.current_time = self.now.strftime('%Y-%m-%d_%H-%M-%S')
        self.fPos = '/media/dataSSD/%s.mp4' % self.current_time
        # initiate mp4Writer; self.frameSize[::-1] to get array as (width, height)
        self.frameSize = self.xiCam.currentFrame.shape
        self.mp4 = mp4Writer(self.fPos, fps,self.frameSize[::-1], grayFlag=grayFlag)
        # set recording parameters
        self.recFlag = False
        self.durationSEC = durationSEC
        self.fps = fps
        self.maxFrameNo = self.durationSEC*self.fps
        self.timeout = 1 / self.fps
        self.buffer = list()


    def videoPreview(self):
        # loops preview until keyboard interrupt, then continues script
        print('Start live preview')
        self.xiCam.startACQ()
        print('Press ctrl+c to start recording')
        # start preview
        try:
            while True:
                frame = self.xiCam.getImage()
                # resize window to fit workspace but keep aspect ratio
                resizedFrame = cv2.resize(frame, (1162, 968)) 
                cv2.imshow('Preview', resizedFrame)
                # preview with 30 fps irrespective of recording fps
                cv2.waitKey(33)
        # except keyboard interrupt (ctrl+c), close preview window, continue script
        except KeyboardInterrupt:
            cv2.destroyAllWindows()
            pass
        self.xiCam.stopACQ()
        print('Live preview finished')


    def mp4Write(self):
        # call mp4Writer class write() function with timeout equal to time between consecutive frames
        try:
            if __name__ == '__main__':
                p = mp.Process(target=self.mp4.write(self.buffer.pop(0)))
                p.start()
                p.join(self.timeout)
                if p.is_alive():
                    print('Warning: Write speed not sufficient')
                    p.join
        # continues recording after warning message 
        except:
            pass

    def recTime(self):
        now = datetime.now()
        start_time = now.strftime("%H:%M:%S, %Y-%m-%d")
        then = now + timedelta(seconds=self.durationSEC)
        end_time = then.strftime("%H:%M:%S, %Y-%m-%d")
        duration = "Recording started: %s\nRecording finishes: %s" % (start_time, end_time)
        return duration

    def main(self):
        # start preview
        self.videoPreview()
        # start recording
        print('\nStart Recording')
        self.xiCam.startACQ()
        print(self.recTime())
        self.recFlag = True
        c = 0
        while  c < self.maxFrameNo or self.buffer:
            if c < self.maxFrameNo:
                c += 1
                self.buffer.append(self.xiCam.getImage())
                self.mp4Write()
            else:
                if self.recFlag == True:
                    self.xiCam.stopACQ
                    self.recFlag = False
                self.mp4Write()
        print('Recording finished!\n')
        self.xiCam.close()
        self.mp4.close()


# xiRecorder('/file/path.mp4', exposure in µs, fps, ROI size in pixels (x, y), ROI offset in pixels (x, y), duration in seconds)
# ROI size of 1200x1000, total size of 2048x1088; offset of (424, 44) to center ROI in camera image
# press ctrl+c to exit preview and start recording
xiR = xiRecorder(83000, 10, (1200, 1000), (424, 44), 86400)
xiR.main()
