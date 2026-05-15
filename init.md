This is a education system for point-to-piont education, or point to small group education
The whole project will be finished using python and can be installed using conda 
In the future it can be convert to othher languages
You can use opensource UI framework and network frame work for python
Both linux and windows can install the package
the cybersecurity should also be considered

This software will using the touchPad of the writing on the screen 
Pre request: we have a touchpad paint pacakge, to read the input of the touchpad of the laptop
and the canvas is indicated in the screen with a dash box,
with around 1/2 heghtx 1/3 width of the screen when there is 1 finger, it works as pen, draw in the screen
if with two finger, it move the canvas away, while the paint is not moving, still in the original location
so we can start draw in the new location without change the old input 
Also we have ereasa and clean button, click ereasa, the component will  using mouse as input 
for the location to erease the draw in the screen, and the clean button just reset the draw
esc will escape the erease model, there is also a button to stop the component.  


So the basic idea of the architecture of the package is that:
The students and teather all in home network, so not static IP
I will have an google claude machine for all the user to connect as an hub
but the google claude are used act as the hub for connect each other 
the network data is not go through the google cloud VM, but go throuh user's network 
The teacher's machine is a server, and the students is client 

we have several component: 

1, the main component, run at the server and client. Work like a zoom. Every user has an account
(the google VM will work as account server too), and the teacher account can intialize a 
meeting, with the meeting, the student can attend. The coordination is down through 
the google cloud VM, but the main computation/execution is done in the server and client. 
Is like, the teacher send initial message to the VM, the client will locally start 
the iterface and ask the VM for the teacher's server IP and connected to teacher's server
running on teacher's computer.  

2, when it is attend, the meeting put the camera function as placholdr for next version, 
but only support the voice talk. 

3, However, the will be content sharing for the instruction/teaching, it looks like share screen
but not real "share the screen", they have no video stream transfer, but the content synchronization
like, "synchronize a pdf page at begining to display at screen of teacher and student(s)", 
synchronize the paint made by the touchpad paint package, this share can accept 
pdf file as the synchronize image, however, it will not edit the pdf file 
just take the pdf file as image to share on both screen, and the teacher's 
paint will be exist at the student's view, so the paint works if the teacher want 
to demonstration how to solve the question. 

5, the AI assistant component (extra part as next phase development):
The software also contains an AI component,  it is for photo "scanner through camera"
it convert the camera photo as input (usually this photo is not in high quality 
such as wrong direction and position, the edge of the paper is not flat)
, and using that camera image input to create a image like it was "scanned" 

and question segament: 
If a teacher configured a multi mode LLM API key, 
this component will using the LLM to accept the "scan quality image" math question, 
recognize the question, and generate the 
PDF file for the questions as exam sheet, each page have 1 question and rest of page is  blank space.

this is basically the architecture of the software, you can using the best opens source 
package you can find (i.e. the GUI pacakge for python, the simplified server and account management)

There is "central sevice server" running on google cloud I am still try to figure out how to setup it.



