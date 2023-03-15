"""
Python modules
"""
print("Loading modules...")
### System modules
import os
import signal
import random
import argparse
import time

print("\n...system modules loaded...")

### Math modules

### Device modules

### Import Stable Diffusion module, Tensorflow version
from stable_diffusion_tf.stable_diffusion import StableDiffusion
print("...Stable Diffusion module loaded...")
import tensorflow as tf

print("...TensorFlow module loaded...")

### Import PyTorch for converting pytorch models to tensorflow

import torch as torch

### Image saving after generation modules
from PIL import Image
from PIL.PngImagePlugin import PngInfo

print("...image modules loaded...")

### WebUi Modules
import gradio as gr

print("...WebUI module loaded...")

### Misc Modules
import utilities.modelFinder as modelFinder
import utilities.settingsControl as settingsControl
import utilities.readWriteFile as readWriteFile
import utilities.videoUtilities as videoUtil
import utilities.tensorFlowUtilities as tensorFlowUtilities
from utilities.consoleUtilities import color

print("...all modules loaded!")

"""
Global variables
"""

### Global Variables
print(color.BOLD,"\nCreating global variables...",color.END)
endProgramVariable = False
model = None
dreamer = None
deviceChoice = None

# Try loading custom settings from user file, otherwise continue with factory settings
userSettings = settingsControl.loadSettings("userData/userPreferences.txt")
if userSettings is False: # This means loadSettings() couldn't find the file. Time to create one
    # The factory settings are hard coded in the settingsControl.py file under createUserPreferences()
    userSettings = settingsControl.createUserPreferences(
        fileLocation = "userData/userPreferences.txt"
    )

## Prompt Settings
try:
    starterPrompt = settingsControl.loadSettings("userData/promptGenerator.txt", 1)
except Exception as e:
    print(e)
    starterPrompt = []

print("...global variables created!")

### Command Line (CLI) Overrides:

parser = argparse.ArgumentParser()

parser.add_argument(
    "--share",
    default = False,
    action = "store_true",
    help = "Share Gradio app publicly",
)

parser.add_argument(
    "--inBrowser",
    default = False,
    action = "store_true",
    help = "Automatically launch app in web browser",
)

CLIOverride = parser.parse_args()

"""
Functions
"""

def addToPrompt(originalPrompt, embeddings, slotA, slotB, slotC, slotD, slotE):
    # Combine slots into a list (because we can't pass a list of gradio components into a gradio command)
    # Number of slots isn't limted to 5, but currently hardcoded as such
    additionList = [embeddings, slotA, slotB, slotC, slotD, slotE]
    addition = ""
    for item in additionList:
        if item != "":
            if addition == "":
                addition = str(item)
            else:
                addition = addition + ", " + str(item)
    
    if originalPrompt == "" or None:
        newPrompt = str(addition)
    else:
        newPrompt = str(originalPrompt) + ", " + str(addition)

    return newPrompt, gr.update(value = ""), gr.update(value = ""), gr.update(value = ""), gr.update(value = ""), gr.update(value = "")

def analyzeModelWeights(model, VAE, textEmbeddings, whichModel):
    if whichModel == "VAE":
        thePatient = VAE
        filePath = userSettings["VAEModelsLocation"]
        dictionaryToFind = "state_dict"
        fileType = ".ckpt"
    elif whichModel == "Text Embeddings":
        thePatient = textEmbeddings
        filePath = userSettings["EmbeddingsLocation"]
        dictionaryToFind = "All"
        if "pt" in thePatient:
            fileType = ".pt"
        else:
            fileType = ".bin"
    elif whichModel == "ControlNet":
        thePatient = model
        filePath = userSettings["modelsLocation"]
        dictionaryToFind = "All"
        fileType = ".pth"
    elif whichModel == "Entire Model":
        thePatient = model
        filePath = userSettings["modelsLocation"]
        dictionaryToFind = "state_dict"
        if ".ckpt" in thePatient:
            fileType = ".ckpt"
        else:
            print("\nUnable to analyze model.\n",thePatient,"was given, which is not a pytorch .ckpt file. Most likely a ControlNet model was given")
            return
    print("\nAnalyzing model weights for: ", thePatient)

    print("...analyzing...")

    pytorchWeights = torch.load(filePath + thePatient, map_location = "cpu")

    """for key, value in pytorchWeights.items():
            valueCheck = str(value)
            if "tensor" in valueCheck:
                print(str(key))
                for token, vector in value.items():
                    print(vector)
                    print(vector.detach().numpy())
                print(value.numpy())
                pytorchWeights.append(str(key))
                pytorchWeights.append(value.numpy())

    print(pytorchWeights)"""
    print("...done!")

    print("Saving analysis...")
    
    if readWriteFile.writeToFile(filePath + thePatient.replace(fileType,"-analysis.txt"), pytorchWeights, dictionaryToFind):
        print("...done!")
    
    del pytorchWeights

def checkModel(selectedModel, legacy):
    # load our main object/class
    global dreamer

    dreamer.pytorchModel = selectedModel

    dreamer.legacy = legacy

    # Have we compiled any models already?
    if dreamer.generator is None:
        print(color.WARNING,"\nNo Stable Diffusion model compiled!\nThere must be a compiled model to analyze.\nCompiling now...",color.END)
        dreamer.compileDreams()
    
    # Set local variables
    model = dreamer.generator

    print("\nText Encoder Model Summary")
    model.text_encoder.summary()

    print("\nDiffusion Model Summary")
    model.diffusion_model.summary()
    try:
        model.diffusion_model.layers[3].summary()
    except Exception as e:
        print(e)

    print("\nDecoder Model Summary")
    model.decoder.summary()

    print("\nEncoder Model Summary")
    model.encoder.summary()

def checkTime(start, end):
    totalMin = 0
    totalSec = 0
    totalHour = 0

    totalTime = end - start

    if totalTime > 60: #Convert to minutes
        totalMin = totalTime // 60
        totalSec = totalTime - (totalMin)*60
        if totalMin > 60: #Convert to hours
            totalHour = totalMin // 60
            totalMin = totalMin - (totalHour)*60
            print(totalHour,"hr ",totalMin,"min ",totalSec,"sec")
        else:
            print(totalMin,"min ",totalSec,"sec")
    else:
        totalSec = totalTime
        print(totalSec,"seconds")

    return totalTime

def createDeviceComponent(devices):
    deviceNames = []
    for device in devices:
        deviceNames.append(device['name'])
    
    if len(devices) > 1:
        active = True
    else:
        active = False

    radioComponent = gr.Radio(
        choices = deviceNames,
        value = deviceNames[0],
        label = "Render Device",
        interactive = active
    )

    return radioComponent

def createPromptComponents(variable):
    totalComponents = []
    for key in variable:
        component = gr.Dropdown(
            choices = variable[key],
            label = str(key),
            value = None
        )

        totalComponents.append(component)

    return totalComponents

def endProgram():
    pid = os.getpid()
    os.kill(pid, signal.SIGINT)

def randomSeed():
    newSeed = random.randint(0, 2 ** 31)
    return newSeed

def saveModel(
    name = "model",
    pytorchModel = None,
    legacyMode = None
):
    # load our main object/class
    global dreamer
    global modelsWeights
    type = ".h5"

    if dreamer.pytorchModel is None:
        print(color.WARNING,"\nNo Stable Diffusion model compiled!\nThere must be a compiled model to save.\nCompiling now...",color.END)
        if pytorchModel is None:
            if userSettings["defaultModel"] != "":
                dreamer.pytorchModel = userSettings["defaultModel"]
            else:
                dreamer.pytorchModel = modelsWeights[0]
        else:
            dreamer.pytorchModel = pytorchModel
        dreamer.legacy = legacyMode

    # Have we compiled any models already?
    if dreamer.generator is None or dreamer.generator.textEmbeddings is not None:
        print("Compiling models without Text Embeddings")
        dreamer.compileDreams(embeddingChoices = False)
    
    # Load/create folder to save frames in
    path = f"models/{name}"
    if not os.path.exists(path): #If it doesn't exist, create folder
        os.makedirs(path)

    # Set local variables
    model = dreamer.generator
    fileName = []

    for modelType in ["text_encoder", "diffusion_model", "decoder", "encoder"]:
        fileName.append(path + "/" + modelType + type)
    
    # Save Text Encoder
    print("\nSaving text encoder model as:\n",fileName[0])
    model.text_encoder.save(fileName[0])
    print(color.GREEN,"Model saved!",color.END)

    # Save Diffusion Model
    print("\nSaving diffusion model as:\n",fileName[1])
    model.diffusion_model.save(fileName[1])
    print(color.GREEN,"Model saved!",color.END)

    # Save Decoder
    print("\nSaving decoder model as:\n",fileName[2])
    model.decoder.save(fileName[2])
    print(color.GREEN,"Model saved!",color.END)

    # Save Encoder
    print("\nSaving encoder model as:\n",fileName[3])
    model.encoder.save(fileName[3])
    print(color.GREEN,"Model saved!",color.END)

    print(color.GREEN,"Finished saving models!",color.END)

def switchResult(type):

    if type == "Art":
        artResult = gr.Gallery.update(visible = True)
        videoResult = gr.Video.update(visible = False)
        return artResult, videoResult

    elif type == "Cinema":
        artResult = gr.Gallery.update(visible = False)
        videoResult = gr.Video.update(visible = True)
        return artResult, videoResult

def userSettingsBool(setting):
    if setting == "True":
        return True
    else:
        return False

"""
Classes
"""

print(color.BOLD,"\nCreating classes...",color.END)

class dreamWorld:
    def __init__(
        self,
        prompt = "Soldiers fighting, close up, European city, steam punk, in the style of Jakub Rozalski, Caravaggio, volumetric lighting, sunset, cinematic lighting, highly detailed, masterpiece, fog, explosions ,depth of field",
        negativePrompt = "horses, ships, water, boat, modern, jpeg artifacts",
        width = 512,
        height = 512,
        scale = 7.5,
        steps = 32,
        seed = None,
        input_image = None,
        input_image_strength = 0.5,
        pytorchModel = None,
        batchSize = 1,
        saveSettings = True,
        jitCompile = True,
        animateFPS = 12,
        totalFrames = 24,
        VAE = "Original",
        textEmbedding = None
    ):
        ## Let's create an object class that we can update later

        ## Set object variables
        self.prompt = prompt
        self.negativePrompt = negativePrompt
        self.width = width
        self.height = height
        self.scale = scale
        self.steps = steps
        self.seed = seed
        self.input_image = input_image
        self.input_image_strength = input_image_strength
        self.pytorchModel = pytorchModel
        self.VAE = VAE
        self.textEmbedding = textEmbedding
        self.embeddingChoices = None
        self.batchSize = batchSize
        self.saveSettings = saveSettings
        self.jitCompile = jitCompile
        self.animateFPS = animateFPS
        self.videoFPS = 24
        self.totalFrames = totalFrames
        self.generator = None
        self.legacy = True
        self.mixedPrecision = False
        self.sampleMethod = None
        self.optimizerMethod = "nadam"

        ## Object variable corrections
        # Set seed if not given
        if self.seed is None or 0:
            self.seed = random.randint(0, 2 ** 31)

    def compileDreams(self, embeddingChoices = None):

        # Time Keeping
        start = time.perf_counter()

        global model
        global userSettings

        print(color.BLUE, color.BOLD,"\nStarting Stable Diffusion with Tensor flow and Apple Metal\n",color.END)
        
        ## Object variable corrections
        # Set seed if not given
        if self.seed is None or 0:
            self.seed = random.randint(0, 2 ** 31)
        
        # Are we using a pytroch model? If downloadWeights is false, then yes we are!
        if self.pytorchModel != "Stable Diffusion 1.4":
            if self.pytorchModel is None:
                self.pytorchModel = userSettings["defaultModel"]
            modelLocation = userSettings["modelsLocation"] + self.pytorchModel
            model = self.pytorchModel
        
        if self.VAE != "Original":
            VAELocation = userSettings["VAEModelsLocation"] + self.VAE
        else:
            VAELocation = "Original"
        
        if embeddingChoices is not None:
            textEmbedding = []
            # print("Embedding Choices:",embeddingChoices)
            for choice in embeddingChoices:
                choice = choice.replace("<","")
                choice = choice.replace(">","")
                for embedding in self.textEmbedding:
                    if choice in embedding.lower():
                        print("Found <"+choice+"> as",embedding)
                        textEmbedding.append(embedding)
            if len(textEmbedding) == 0:
                print("\nFound no text embeddings")
                textEmbedding = None
            else:
                textEmbedding.insert(0,self.textEmbedding[0])
                # print("Passing these into model:\n",textEmbedding)
        else:
            textEmbedding = None

        # Create generator with StableDiffusion class
        self.generator = StableDiffusion(
            imageHeight = int(self.height),
            imageWidth = int(self.width),
            jit_compile = self.jitCompile,
            pyTorchWeights = modelLocation,
            legacy = self.legacy,
            VAE = VAELocation,
            textEmbeddings = textEmbedding,
            mixedPrecision = self.mixedPrecision
        )
        
        print(color.GREEN,color.BOLD,"\nModels ready!",color.END)

        # Time keeping
        end = time.perf_counter()
        checkTime(start, end)
    
    def create(
        self,
        type = "Art", # Which generation function to call. Art = still, Cinema = video
        prompt = "dinosaur riding a skateboard, cubism, textured, detailed",
        negativePrompt = "frame, framed",
        width = 512,
        height = 512,
        scale = 7.5,
        steps = 32,
        seed = None,
        inputImage = None,
        inputImageStrength = 0.5,
        pytorchModel = "StableDiffusion_V1p5.ckpt",
        batchSize = 1,
        saveSettings = True,
        projectName = "noProjectNameGiven",
        animateFPS = 12, # Starting from here down are video specific variables
        videoFPS = 24,
        totalFrames = 24,
        seedBehavior = "iter",
        saveVideo = True,
        angle = float("0"),
        zoom = float("1"),
        xTranslation = "0",
        yTranslation = "0",
        startingFrame = 0,
        legacy = True,
        VAE = "Original",
        embeddingChoices = None,
        mixedPrecision = True,
        sampleMethod = None,
        optimizerMethod = "nadam",
        deviceOption = '/gpu:0'
    ):
        
        # Import global variables
        global deviceChoice

        # Update object variables that don't trigger a re-compile
        self.prompt = prompt
        self.negativePrompt = negativePrompt
        self.scale = scale
        self.steps = steps
        self.seed = seed
        self.input_image = inputImage
        self.input_image_strength = inputImageStrength
        self.saveSettings = saveSettings
        self.batchSize = batchSize

        # Video object variables that don't trigger re-compile
        self.animateFPS = animateFPS
        self.videoFPS = videoFPS
        self.totalFrames = int(totalFrames)
        self.sampleMethod = sampleMethod

        # Modes
        self.legacy = legacy
        if mixedPrecision is True:
            self.mixedPrecision = mixedPrecision
            if self.generator is not None:
                self.generator.changePolicy("mixed_float16")
        else:
            self.mixedPrecision = mixedPrecision
            if self.generator is not None:
                self.generator.changePolicy("float32")

        # Device Selection
        for device in deviceChoice:
            if device['name'] == deviceOption:
                selectedDevice = device['TensorFlow'].name[-1]
                if "CPU" in device['TensorFlow'].name:
                    print(color.CYAN,"\nUsing CPU to render:\n",device['name'],color.END)
                    selectedDevice = "/device:CPU:" + selectedDevice
                elif "GPU" in device['TensorFlow'].name:
                    print(color.CYAN,"\nUsing GPU to render:\n",device['name'],color.END)
                    selectedDevice = "/GPU:" + selectedDevice

        with tf.device(selectedDevice):

            # Update object variables that trigger a re-compile
            if width != self.width or height != self.height or pytorchModel != self.pytorchModel or VAE != self.VAE or embeddingChoices != self.embeddingChoices:
                print(color.WARNING,"\nCritical changes made for creation, compiling new model",color.END)
                print("New inputs: \n","Width:",width,"Height:",height,"Batch Size:",batchSize,"Model:",pytorchModel,"\nEmbeddings:",embeddingChoices)
                print("Old inputs: \n","Width:",self.width,"Height:",self.height,"Batch Size:",self.batchSize,"Model:",self.pytorchModel,"\nEmbeddings:",self.embeddingChoices)
                # Load all of the re-compile variables
                self.width = int(width)
                self.height = int(height)
                self.pytorchModel = pytorchModel
                self.VAE = VAE
                self.embeddingChoices = embeddingChoices

                # Compile new model baesd on new parameters
                self.compileDreams(embeddingChoices = embeddingChoices)
            else:
                # Load all of the re-compile variables, but nothing has changed
                self.width = int(width)
                self.height = int(height)
                self.pytorchModel = pytorchModel
                self.VAE = VAE

            if optimizerMethod is not self.optimizerMethod and self.generator is not None:
                self.generator.compileModels(optimizerMethod, True)
                self.optimizerMethod = optimizerMethod

            # Global Variables
            global model

            # What to create?

            if type == "Art":
                # Create still image(s)
                result = self.generateArt(sampleMethod = self.sampleMethod)

                videoResult = None

                return result, videoResult
            elif type == "Cinema":
                # Create video
                result = None
                videoResult = self.generateCinema(
                    projectName = projectName,
                    seedBehavior = seedBehavior,
                    angle = angle,
                    zoom = zoom,
                    xTranslation = xTranslation,
                    yTranslation = yTranslation,
                    saveVideo = saveVideo,
                    startingFrame = int(startingFrame),
                    sampleMethod = self.sampleMethod
                )
                
                return result, videoResult

    def generateArt(
            self,
            sampleMethod = None
        ):
        # Global variables
        global userSettings
        
        # Time Keeping
        start = time.perf_counter()

        # Before creation/generation, do we have a compiled?
        if self.generator is None:
            self.compileDreams()

        print(color.PURPLE, "\nGenerating ",self.batchSize," image(s) of:", color.END)

        print(self.prompt)

        # Use the generator function within the newly created class to generate an array that will become an image
        imgs = self.generator.generate(
            prompt = self.prompt,
            negativePrompt = self.negativePrompt,
            num_steps = self.steps,
            unconditional_guidance_scale = self.scale,
            temperature = 1,
            batch_size = self.batchSize,
            seed = self.seed,
            input_image = self.input_image,
            input_image_strength = self.input_image_strength,
            sampler = sampleMethod
        )

        print(color.BOLD, color.GREEN, "\nFinished generating!")

        ### Create final image from the generated array ###

        # Generate PNG metadata for reference
        metaData = self.createMetadata()

        # Save settings
        if self.saveSettings is True:
            readWriteFile.writeToFile("creations/" + str(self.seed) + ".txt", [self.prompt, self.negativePrompt, self.width, self.height, self.scale, self.steps, self.seed, self.pytorchModel, self.batchSize, self.input_image_strength, self.animateFPS, self.videoFPS, self.totalFrames, "Positive Iteration", "0", "0", "0", "0"])

        # Multiple Image result:
        for img in imgs:
            print("Processing image(s)...")
            imageFromBatch = Image.fromarray(img)
            imageFromBatch.save(userSettings["creationLocation"] + str(int(self.seed)) + str(int(self.batchSize)) + ".png", pnginfo = metaData)
            print("...image(s) saved!\n")
            self.batchSize = self.batchSize - 1

        print("Returning image!",color.END)

        # Time keeping
        end = time.perf_counter()
        checkTime(start, end)

        return imgs
    
    def generateCinema(
        self,
        projectName = "noProjectNameGiven",
        seedBehavior = "Positive Iteration",
        angle = float("0"),
        zoom = float("1"),
        xTranslation = "0",
        yTranslation = "0",
        saveVideo = True,
        startingFrame = 0,
        sampleMethod = None
    ):

        # Before creation/generation, did we compile the model?
        if self.generator is None:
            self.compileDreams()
        
        # Load in global variables
        global userSettings

        print(color.PURPLE, "\nGenerating frames of:", color.END)

        print(self.prompt)

        # Local variables
        seed = self.seed
        previousFrame = self.input_image
        currentInputFrame = None
        renderTime = 0

        # Load/create folder to save frames in
        path = f"content/{projectName}"
        if not os.path.exists(path): #If it doesn't exist, create folder
            os.makedirs(path)
        print("\nIn folder: ",path)

        # Movement variables
        angle = float(angle)
        zoom = float(zoom)

        if xTranslation is None:
            xTranslation = "0"
        
        if yTranslation is None:
            yTranslation = "0"
        
        print("...giving camera direction...")
        originalTranslations = [xTranslation, yTranslation]
        
        xTranslation = videoUtil.generate_frames_translation(xTranslation, self.totalFrames)
        yTranslation = videoUtil.generate_frames_translation(yTranslation, self.totalFrames)

        # Save settings BEFORE running generation in case it crashes

        if self.saveSettings is True:
            readWriteFile.writeToFile(path + "/" + str(self.seed) + ".txt", [self.prompt, self.negativePrompt, self.width, self.height, self.scale, self.steps, self.seed, self.pytorchModel, self.batchSize, self.input_image_strength, self.animateFPS, self.videoFPS, self.totalFrames, seedBehavior, angle, zoom, originalTranslations[0], originalTranslations[1]])
        
        # Create frames
        for item in range(0, (self.totalFrames) ): # Minus 1 from total frames because we're starting at 0 instead of 1 when counting up. User asks for 24 frames, computer counts from 0 to 23

            # Time Keeping
            start = time.perf_counter()

            # Update frame number
            # If starting frame is given, then we're also adding every iteration to the number
            frameNumber = item + startingFrame

            print("\nGenerating Frame ",frameNumber)

            # Continue camera movement from prior frame if starting frame was given
            if startingFrame > 0 and item == 0:
                print("...continuing camera movement...")
                previousFrame = videoUtil.animateFrame2DWarp(
                    previousFrame,
                    angle = angle,
                    zoom = zoom,
                    xTranslation = xTranslation[item],
                    yTranslation = yTranslation[item],
                    width = self.width,
                    height = self.height
                )
            
            # Color management
            """if currentInputFrame is not None:
                previousFrame = videoUtil.maintain_colors(previousFrame, currentInputFrame)"""
            
            # Update previous frame variable for use in the generation of this frame
            currentInputFrame = previousFrame

            ## Create frame
            # frame variable calls the generator to generate an image
            frame = self.generator.generate(
                prompt = self.prompt,
                negativePrompt = self.negativePrompt,
                num_steps = self.steps,
                unconditional_guidance_scale = self.scale,
                temperature = 1,
                batch_size = self.batchSize,
                seed = seed,
                input_image = currentInputFrame,
                input_image_strength = self.input_image_strength,
                sampler = sampleMethod
            )

            ## Save frame
            print(color.GREEN,"\nFrame generated. Saving to: ",path,color.END)

            # Generate metadata for saving in the png file
            metaData = self.createMetadata()

            savedImage = Image.fromarray(frame[0])
            savedImage.save(f"{path}/frame_{frameNumber:05}.png", format = "png", pnginfo = metaData)

            # Store frame array for next iteration
            print("...applying camera movement for next frame...")
            previousFrame = videoUtil.animateFrame2DWarp(
                frame[0],
                angle = angle,
                zoom = zoom,
                xTranslation = xTranslation[item],
                yTranslation = yTranslation[item],
                width = self.width,
                height = self.height
            )

            # Color management
            #if item > 0:
            # previousFrame = videoUtil.maintain_colors(previousFrame, frame[0])
            
            # Memmory Clean Up
            """frame = None
            metaData = None"""
            del frame
            del metaData

            # Update seed
            if seedBehavior == "Positive Iteration":
                seed = seed + 1
            elif seedBehavior == "Random Iteration":
                seed = random.randint(0, 2 ** 31)
            
            # Time keeping
            end = time.perf_counter()
            renderTime = renderTime + checkTime(start, end)
        
        # Finished message and time keeping
        print(color.GREEN,"\nCINEMA! Created in:",color.END)
        checkTime(0, renderTime)
        print("Per frame:")
        checkTime(0, renderTime/(self.totalFrames))

        ## Video compiling
        if saveVideo is True:
            finalVideo = self.deliverCinema(
                path, userSettings["creationLocation"], projectName
            )

            return finalVideo
    
    def deliverCinema(self, imagePath, videoPath, fileName):
        # Video creation

        imagePath = os.path.join(imagePath, "frame_%05d.png")
        videoPath = os.path.join(videoPath, f"{fileName}.mp4")

        videoUtil.constructFFmpegVideoCmd(self.animateFPS, self.videoFPS, imagePath, videoPath)

        return videoPath
    
    def createMetadata(self):
        # Metadata to be stored in the image file
        metaData = PngInfo()
        metaData.add_text('prompt', self.prompt)
        metaData.add_text('negativePrompt', self.negativePrompt)
        metaData.add_text('seed', str(int(self.seed)))
        metaData.add_text('CFG scale', str(int(self.scale)))
        metaData.add_text('steps', str(int(self.steps)))
        metaData.add_text('input image strength', str(int(self.input_image_strength)))

        return metaData

print("...done!")

"""
Models and Weights
    Current supports:
        + Stable Diffusion Models and their variants:
            .ckpt - pytorch
            .h5 - TensorFlow old weights file
            .pth - Will find controlnet models, but will not load
        + VAE models
            .ckpt - pytroch
        + Text Embeddings
            .pt
            .bin
"""

print(color.BOLD,"\nSearching for diffusion models...",color.END)
modelsWeights = modelFinder.findModels(userSettings["modelsLocation"], ".ckpt")
modelsWeights.extend(modelFinder.findModels(userSettings["modelsLocation"], ".pth"))
modelsWeights.extend(modelFinder.findModels(userSettings["modelsLocation"], ""))
modelsWeights.sort()

print(color.BOLD,"\nSearching for VAE models...",color.END)
VAEWeights = modelFinder.findModels(userSettings["VAEModelsLocation"], ".ckpt")
VAEWeights.sort()
VAEWeights.insert(0,"Original")

print(color.BOLD,"\nSearching for text embeddings...",color.END)
embeddingWeights = modelFinder.findModels(userSettings["EmbeddingsLocation"], ".pt")
embeddingWeights.extend(modelFinder.findModels(userSettings["EmbeddingsLocation"], ".bin"))
embeddingWeights.sort()
# Store names with <> around them for prompt generator
embeddingNames = embeddingWeights.copy()
for index, name in enumerate(embeddingNames):
    if "pt" in name:
        embeddingNames[index] = "<" + name.replace(".pt","") + ">"
        embeddingNames[index] = embeddingNames[index].lower()
    if "bin" in name:
        embeddingNames[index] = "<" + name.replace(".bin","") + ">"
        embeddingNames[index] = embeddingNames[index].lower()
# Add the filepath as the first index to the embeddingWeights variable
embeddingWeights.insert(0, userSettings["EmbeddingsLocation"])

print(color.GREEN,color.BOLD,"\nStarting program:",color.END)

"""
Main Class
    This is the variable we'll be referencing in the Web UI
"""
dreamer = dreamWorld(textEmbedding = embeddingWeights)

"""
Main Web Components
    Define components outside of gradio's loop interface
    so they can be accessed regardless of child/parent position in the layout
"""

"""
Main Tools
"""

# Prompts
prompt = gr.Textbox(
    label = "Prompt - What should the AI create?"
)

negativePrompt = gr.Textbox(
    label = "Negative Prompt - What should the AI avoid when creating?"
)

# Creation Type

creationType = gr.Radio(
    choices = ["Art", "Cinema"],
    value = userSettings["creationType"],
    label = "Creation Type:"
)

# Start Button
startButton = gr.Button("Start")

startButton.style(
    full_width = True
)

"""
Settings
"""

## Creation ##
if userSettings["defaultModel"] != "":
    defaultModelValue = modelsWeights[modelsWeights.index(userSettings["defaultModel"])]
else:
    defaultModelValue = modelsWeights[0]

listOfModels = gr.Dropdown(
            choices = modelsWeights,
            label = "Diffusion Model",
            value = defaultModelValue
        )

legacyVersion = gr.Checkbox(
    label = "Use Legacy Stable Diffusion (1.4/1.5)",
    value = userSettingsBool(userSettings["legacyVersion"])
)

# Height
"""height = gr.Dropdown(
    choices = [128,256,384,512,640,768,896,1024],
    value = 512,
    label = "Height"
)"""
height = gr.Slider(
    minimum = 128,
    maximum = 1152,
    value = 512,
    step = 128
)

# Width
"""width = gr.Dropdown(
    choices = [128,256,384,512,768,896,1024],
    value = 512,
    label = "Width"
)"""
width = gr.Slider(
    minimum = 128,
    maximum = 1152,
    value = 512,
    step = 128
)

# Batch Size

batchSizeSelect = gr.Slider(
    minimum = 1,
    maximum = int(userSettings["batchMax"]),
    value = int(userSettings["defaultBatchSize"]),
    step = 1,
    label = "How many results to make?"
)

# Steps
steps = gr.Slider(
    minimum = 2,
    maximum = int(userSettings["stepsMax"]),
    value = int(userSettings["stepsMax"]) / 2,
    step = 1,
    label = "How many times the AI should sample - Higher numbers = better image"
)

# Scale
scale = gr.Slider(
    minimum = 2,
    maximum = int(userSettings["scaleMax"]),
    value = 7.5,
    step = 0.1,
    label = "How closely should the AI follow the prompt - Higher number = follow more closely"
)

# Seed
seed = gr.Number(
    value = random.randint(0, 2 ** 31),
    label = "Unique number for the image created",

)

## Text Embeddings ##
useEmbeddings = gr.Checkbox(
    label = "Use Text Embeddings",
    value = False
)

embeddingChoices = gr.CheckboxGroup(
    choices = embeddingNames,
    label = "Select embeddings to include in model:"
)

## .AdvancedSettings

listOfVAEModels = gr.Dropdown(
            choices = VAEWeights,
            label = "VAE Options",
            value = VAEWeights[0]
        )

deviceChoice = tensorFlowUtilities.listDevices()

listOfDevices = createDeviceComponent(deviceChoice)

sampleChoices = ["Basic", "DPMSolver"]

sampleMethod = gr.Dropdown(
    choices = sampleChoices,
    label = "Sample Method",
    value = sampleChoices[0]
)

optimizerChoices = ["adadelta", "adagrad", "adam", "adamax", "ftrl", "nadam", "RMSprop", "SGD"]

optimizerMethod = gr.Dropdown(
    choices = optimizerChoices,
    label = "Optimizer",
    value = optimizerChoices[5]
)

# Save user settings for prompt

saveSettings = gr.Checkbox(
    label = "Save settings used for prompt creation?",
    value = userSettingsBool(userSettings["saveSettings"])
)

# Mixed precision
mixedPrecisionCheckbox = gr.Checkbox(
    label = "Used mixed precision? (FP16)",
    value = userSettingsBool(userSettings["mixedPrecision"])
)

## Input Image

inputImage = gr.Image(
    label = "Input Image"
)

# Input Image Strength
inputImageStrength = gr.Slider(
    minimum = 0,
    maximum = 1,
    value = 0.5,
    step = 0.01,
    label = "0 = Don't change the image, 1 = ignore image entirely"
)

# Prompt Engineering

starterPrompts = createPromptComponents(starterPrompt)

addPrompt = gr.Button("Add to prompt")

importPromptLocation = gr.File(
    label = "Import Prior Prompt and settings for prompt",
    type = "file"
)

importPromptButton = gr.Button("Import prompt")

listOfEmbeddings = gr.Dropdown(
            choices = embeddingNames,
            label = "Text Embeddings",
            value = embeddingNames[0]
        )

## Video

# Project Name

projectName = gr.Textbox(
    value = "cinemaProject",
    label = "Name of the video - No spaces"
)

# FPS
# Animated
animatedFPS = gr.Dropdown(
    choices = [1,2,4,12,24,30,48,60],
    value = 12,
    label = "Animated Frames Per Second - 12 is standard animation"
)
# Final video
videoFPS = gr.Dropdown(
    choices = [24,30,60],
    value = 24,
    label = "Video Frames Per Second - 24 is standard cinema"
)

# Total frames
totalFrames = gr.Number(
    value = 48,
    label = "Total Frames",
)

# Starting frame

startingFrame = gr.Number(
    value = 0,
    label = "Starting Frame Number"
)

# Seed behavior
seedBehavior = gr.Dropdown(
    choices = ["Positive Iteration", "Negative Iteration", "Random Iteration", "Static Iteration"],
    value = "Positive Iteration",
    label = "Seed Behavior - How the seed changes from frame to frame"
)

# Save video
saveVideo = gr.Checkbox(
    label = "Save result as a video?",
    value = True
)

# Image Movement
# Angle
angle = gr.Slider(
    minimum = 0,
    maximum = 360,
    value = 0,
    step = 1,
    label = "Angle - Camera angle in degrees"
)

# Zoom
zoom = gr.Slider(
    minimum = 0.9,
    maximum = 1.1,
    value = 1,
    step = 0.01,
    label = "Zoom - Zoom in/out - Higher number zooms in"
)

# X Translation
xTranslate = gr.Textbox(
    label = "X Translation - Movement along x-axis",
    value = "-7"
)

# Y Translation
yTranslate = gr.Textbox(
    label = "Y Translation - Movement along y-axis",
    value = "-7"
)

## Gradio.Tools

saveModelName = gr.Textbox(
    label = "Model Name",
    value = "model"
)

saveModelButton = gr.Button("Save model")

pruneModelButton = gr.Button("Optimize Model")

checkModelButton = gr.Button("Check Model")

analyzeModelWeightsButton = gr.Button("Analyze Model Weights")

analyzeThisModelChoices = ["Entire Model", "VAE", "Text Embeddings", "ControlNet"]

analyzeThisModel = gr.Dropdown(
    choices = analyzeThisModelChoices,
    value = analyzeThisModelChoices[0],
    label = "What kind of model to analyze?"
)

# Video Tools
convertToVideoButton = gr.Button("Convert to video")

# input frames
framesFolder = gr.Textbox(
    label = "Frames folder path",
    value = ""
)

# creations location
creationsFolder = gr.Textbox(
    label = "Save Location",
    value = userSettings["creationLocation"]
)

# video name
videoFileName = gr.Textbox(
    label = "Video Name",
    value = "cinema"
)

## Result(s)

# Gallery for still images
result = gr.Gallery(
    label = "Results",
)

result.style(
    grid = 2
)

resultVideo = gr.Video(
    label = "Result",
    visible = False
)

## End Program

endProgramButton = gr.Button(
    "Close Program"
)

"""
Main Layout
    Designed with Gradio's block system
"""

with gr.Blocks(
    title = "Stable Diffusion"
) as demo:
    #Title
    gr.Markdown(
        "<center><span style = 'font-size: 32px'>Stable Diffusion</span><br><span style = 'font-size: 16px'>Tensorflow and Apple Metal<br>Intel Mac</span></center>"
    )

    with gr.Row():
        with gr.Column(
            scale = 3,
            variant = "panel"
        ):
            # Prompts
            prompt.render()
            negativePrompt.render()

        with gr.Column(
            scale = 1,
            variant = "compact"
        ):
            # Creation type
            creationType.render()

            # Start Button
            startButton.render()

    # Image to Image
    with gr.Row():
        with gr.Column():
            with gr.Tab("Settings"):
                with gr.Tab("Creation"):
                    with gr.Row():
                        # Basic Settings
                        with gr.Column():
                            gr.Markdown("<center>Model Options</center>")

                            ## Models
                            # Model Selection
                            listOfModels.render()

                            # Legacy vs Contemporary Edition
                            legacyVersion.render()

                            gr.Markdown("<center>Image dimensions</center>")
                            # Width
                            width.render()

                            # Height
                            height.render()

                            gr.Markdown("<center>Batch Size</center>")
                            # Batch Size
                            batchSizeSelect.render()
                        
                        # Elementary settings
                        with gr.Column():
                            gr.Markdown("<center>Steps</center>")

                            # Steps
                            steps.render()

                            gr.Markdown("<center>Guidance Scale</center>")
                            # Scale
                            scale.render()

                            gr.Markdown("<Center>Seed</center>")

                            with gr.Row():
                                # Seed
                                seed.render()

                                newSeed = gr.Button("New Seed")
                            
                with gr.Tab("Input Image"):
                    ## Input Image
                    gr.Markdown("<center><b><u>Input Image</b></u></center>Feed a starting image into the AI to give it inspiration")

                    inputImage.render()

                    # Input Image Strength

                    gr.Markdown("Strength")

                    inputImageStrength.render()
                
                with gr.Tab("Text Embeddings"):
                    # Text Embeddings
                    # useEmbeddings.render()

                    embeddingChoices.render()

            with gr.Tab("Advanced Settings"):

                with gr.Row():

                    # VAE Selection
                    listOfVAEModels.render()

                    # Sampler Method
                    sampleMethod.render()

                    # Optimizer
                    optimizerMethod.render()

                with gr.Row():

                    # Save settings used for creation?
                    saveSettings.render()

                    # Mixed Precision
                    mixedPrecisionCheckbox.render()

                with gr.Row():
                    # Device Selection
                    listOfDevices.render()

            with gr.Tab("Import"):

                with gr.Tab("Creation"):
                    ## Import prior prompt and settings
                    gr.Markdown("<center><b><u>Import Creation</b></u></center>Import prior prompt and generator settings")
                    
                    importPromptLocation.render()
                    
                    importPromptButton.render()
            
            with gr.Tab("Video"):

                with gr.Tab("Settings"):

                    projectName.render()

                    animatedFPS.render()
                    
                    videoFPS.render()

                    totalFrames.render()

                    startingFrame.render()

                    seedBehavior.render()

                    saveVideo.render()
                
                with gr.Tab("Camera Movement"):

                    angle.render()

                    zoom.render()

                    xTranslate.render()

                    yTranslate.render()
            
            with gr.Tab("Tools"):
                with gr.Tab("Prompt Generator"):
                    gr.Markdown("Tools to generate useful prompts")

                    listOfEmbeddings.render()
                    
                    # Starter Prompts
                    for item in starterPrompts:
                        item.render()

                    addPrompt.render()
                with gr.Tab("Model Conversion"):

                    gr.Markdown("<center><b>Save Current model as Keras '.h5' weights</b><br>Useful for converting PyTorch '.ckpt' to Keras '.h5'</center>")

                    with gr.Row():

                        saveModelName.render()

                        saveModelButton.render()
                    
                    #pruneModelButton.render()
                
                with gr.Tab("Video Tools"):
                    gr.Markdown("<center>Image sequence to video</center>")
                    with gr.Row():

                        with gr.Column():

                            framesFolder.render()

                            creationsFolder.render()
                        
                        with gr.Column():

                            videoFileName.render()

                            convertToVideoButton.render()
                
                with gr.Tab("PyTorch Model Analysis"):
                    gr.Markdown("<center>What makes a pytroch model tick?</center>")

                    checkModelButton.render()

                    analyzeModelWeightsButton.render()

                    analyzeThisModel.render()

        with gr.Column():
            # Result
            with gr.Column():
                gr.Markdown("<center><span style = 'font-size: 24px'><b>Result</b></span></center>")
                
                result.render()

                resultVideo.render()
    
    with gr.Row():

        endProgramButton.render()

    ## Event actions

    # When start button is pressed
    startButton.click(
        fn = dreamer.create,
        inputs = [
            creationType,
            prompt,
            negativePrompt,
            width,
            height,
            scale,
            steps,
            seed,
            inputImage,
            inputImageStrength,
            listOfModels,
            batchSizeSelect,
            saveSettings,
            projectName,
            animatedFPS,
            videoFPS,
            totalFrames,
            seedBehavior,
            saveVideo,
            angle,
            zoom,
            xTranslate,
            yTranslate,
            startingFrame,
            legacyVersion,
            listOfVAEModels,
            embeddingChoices,
            mixedPrecisionCheckbox,
            sampleMethod,
            optimizerMethod,
            listOfDevices
        ],
        outputs = [result, resultVideo]
    )
    
    # When new seed is pressed
    newSeed.click(
        fn = randomSeed,
        inputs = None,
        outputs = seed,
    )

    # When add prompt is pressed
    addPrompt.click(
        fn = addToPrompt,
        inputs = [prompt, listOfEmbeddings, starterPrompts[0], starterPrompts[1], starterPrompts[2], starterPrompts[3], starterPrompts[4]],
        outputs = [prompt, starterPrompts[0], starterPrompts[1], starterPrompts[2], starterPrompts[3], starterPrompts[4]]
    )

    # When import button is pressed
    importPromptButton.click(
        fn = readWriteFile.readFromFile,
        inputs = importPromptLocation,
        outputs = [
            prompt,
            negativePrompt,
            width,
            height,
            scale,
            steps,
            seed,
            listOfModels,
            batchSizeSelect,
            inputImageStrength,
            animatedFPS,
            videoFPS,
            totalFrames,
            seedBehavior,
            angle,
            zoom,
            xTranslate,
            yTranslate
        ]
    )

    # When creation type is selected
    creationType.change(
        fn = switchResult,
        inputs = creationType,
        outputs = [result, resultVideo]
    )

    ## Tools

    # Save Model

    saveModelButton.click(
        fn = saveModel,
        inputs = [saveModelName, listOfModels, legacyVersion],
        outputs = None
    )

    # Check Model

    checkModelButton.click(
        fn = checkModel,
        inputs = [listOfModels, legacyVersion],
        outputs = None
    )

    convertToVideoButton.click(
        fn = dreamer.deliverCinema,
        inputs = [framesFolder, creationsFolder, videoFileName],
        outputs = resultVideo
    )

    analyzeModelWeightsButton.click(
        fn = analyzeModelWeights,
        inputs = [
            listOfModels,
            listOfVAEModels,
            listOfEmbeddings,
            analyzeThisModel,
        ],
        outputs = None
    )

    ## End Program

    endProgramButton.click(
        fn = endProgram,
        inputs = None,
        outputs = None
    )

"""
Final Steps
"""

print(color.BLUE,"\nLaunching Gradio:\n",color.END)

demo.launch(
    inbrowser = CLIOverride.inBrowser,
    show_error = True,
    share = CLIOverride.share
)