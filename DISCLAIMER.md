# Disclaimer

**READ THIS BEFORE USING ANY SOFTWARE OR INFORMATION IN THIS REPOSITORY.**

## Not a Medical Project

This project is an independent reverse engineering effort to understand the Bluetooth Low Energy (BLE) communication protocol used by Bluetens TENS/EMS devices. It is **not** a medical project, **not** affiliated with Bluetens or any medical device manufacturer, and **not** intended to provide medical treatment, therapy, diagnosis, or advice of any kind.

Nothing in this repository should be interpreted as medical guidance. Do not use this software as a substitute for professional medical advice, diagnosis, or treatment. Always consult a qualified healthcare provider before using any electrical stimulation device.

## Electrical Stimulation Hazards

TENS (Transcutaneous Electrical Nerve Stimulation) and EMS (Electrical Muscle Stimulation) devices deliver electrical current through the body. Improper use of these devices can cause serious injury or death. Known hazards include but are not limited to:

- **Cardiac risk**: Electrical stimulation near the chest, across the heart, or on the neck/throat can interfere with cardiac rhythm and may cause cardiac arrest, particularly in individuals with pacemakers, implantable defibrillators, or other cardiac implants.
- **Seizures**: Stimulation near the head or transcerebrally may trigger seizures.
- **Burns**: Incorrect electrode placement, damaged electrodes, or excessive intensity can cause electrical burns to the skin.
- **Muscle damage**: Excessive intensity or prolonged stimulation can cause muscle injury, spasms, or rhabdomyolysis.
- **Interference with medical devices**: Electrical stimulation can interfere with pacemakers, insulin pumps, and other implanted or external medical devices.
- **Pregnancy risk**: Electrical stimulation should not be used on the abdomen or lower back during pregnancy.
- **Skin irritation**: Electrode adhesives and electrical current may cause skin irritation, allergic reactions, or contact dermatitis.

This software allows direct low-level control of stimulation parameters (frequency, pulse width, intensity) without the safety guardrails present in the manufacturer's official application. **Using this software increases the risk of harm compared to using the official app.**

## No Safety Validation

The protocol information in this repository was obtained through reverse engineering of a decompiled mobile application. It has **not** been validated against official manufacturer documentation, tested by qualified biomedical engineers, or reviewed for safety compliance. The reverse-engineered protocol may contain errors, omissions, or misunderstandings that could result in unintended device behavior.

The scripts and tools provided here:

- Have not been certified or approved by any regulatory body (FDA, CE, or equivalent)
- Have not undergone safety testing of any kind
- May send commands to the device that are outside its safe operating parameters
- May cause the device to behave in ways not intended by the manufacturer
- Bypass any safety mechanisms implemented in the official application

## OTA Firmware Updates

This repository documents the OTA (Over-The-Air) firmware update protocol. **Flashing unauthorized firmware can permanently damage ("brick") the device** and may void any warranty. The OTA protocol uses CRC16 for data integrity only -- there is no cryptographic signature verification. Do not attempt firmware modifications unless you fully understand the risks and are prepared for permanent device failure.

## Assumption of Risk

By using any software, code, documentation, or information from this repository, you acknowledge and agree that:

1. You are solely responsible for any consequences resulting from your use of this material.
2. You understand the risks of electrical stimulation and accept those risks voluntarily.
3. You will not use this software on any person (including yourself) without fully understanding the hazards described above.
4. You will not use this software on any person with a pacemaker, implantable defibrillator, or other implanted electronic device.
5. You will not use this software on or near the head, neck, chest, or heart.
6. You will not use this software during pregnancy.
7. You will not use this software on minors or on individuals who cannot provide informed consent.

## No Warranty

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. THE ENTIRE RISK AS TO THE QUALITY, SAFETY, AND PERFORMANCE OF THE SOFTWARE IS WITH YOU.

## Limitation of Liability

IN NO EVENT SHALL THE AUTHORS, CONTRIBUTORS, OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. THIS INCLUDES BUT IS NOT LIMITED TO ANY PERSONAL INJURY, PROPERTY DAMAGE, DEVICE DAMAGE, OR DEATH RESULTING FROM THE USE OF THIS SOFTWARE.

## Intended Audience

This repository is intended for educational and research purposes only. It is meant for individuals with technical knowledge of BLE protocols, embedded systems, and electrical stimulation who wish to study the communication protocol of these devices. It is not intended for end users seeking to control a TENS/EMS device for therapeutic use.
