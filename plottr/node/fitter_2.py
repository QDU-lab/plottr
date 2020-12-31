import sys
import os
import pkgutil
import importlib
from importlib import reload, import_module
import warnings
from typing import Dict, Optional, Type, Callable
import inspect
from dataclasses import dataclass
import numbers

import lmfit
from lmfit import Parameter as lmParameter, Parameters as lmParameters

from plottr import QtGui, QtCore, Slot, Signal, QtWidgets
from plottr.analyzer import fitters
from plottr.analyzer.fitters.fitter_base import Fit

from ..data.datadict import DataDictBase
from .node import Node, NodeWidget, updateOption, updateGuiFromNode

__author__ = 'Chao Zhou'
__license__ = 'MIT'

def get_models_in_module(module):
    '''Gather the model classes in the the fitting module file
    :return : a dictionary that contains all the model classed in the module
    '''
    def is_Fit_subclass(cls: Type[Fit]):
        """ check if a class is the subclass of analyzer.fitters.fitter_base.Fit
        """
        try:
            if issubclass(cls, Fit) and (cls is not Fit):
                return True
            else:
                return False
        except TypeError:
            return False
    # reload the module (this will clear the class cache)
    try:
        del sys.modules[module.__name__]
    except:
        pass
    module = import_module(module.__name__)

    model_classes = inspect.getmembers(module, is_Fit_subclass)
    model_dict = {}
    for mc in model_classes:
        model_dict[mc[0]] = mc[1]
    return model_dict

def get_modules_in_pkg(pkg):
    '''Gather the fitting modules in a package
    '''
    modules = {}
    for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
        if modname != "fitter_base":
            module_ = import_module('.'+modname, pkg.__name__)
            try:
                del sys.modules[module_.__name__]
            except:
                pass
            module_ = import_module('.'+modname, pkg.__name__)
            modules[modname] = module_
    return modules


INITIAL_MODULES = get_modules_in_pkg(fitters)
#TODO: this requires putting the modules in the init of fitters, there should
# be a better way to do this.

# OPEN_MODULE_ICON = QtGui.QIcon(QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon))
# REFRESH_MODULE_ICON = QtGui.QIcon(QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))

MAX_FLOAT = sys.float_info.max

DEBUG = 1



@dataclass
class FittingOptions:
    model: Type[Fit]
    parameters: lmParameters


class FittingGui(NodeWidget):
    """ Gui for controlling the fitting function and the initial guess of
    fitting parameters.
    """
    def __init__(self, parent=None, node=None):
        super().__init__(parent)
        self.input_options = None # fitting option in dataIn
        self.live_update = False
        self.param_signals = []
        self.fitting_modules = INITIAL_MODULES

        self.layout = QtWidgets.QFormLayout()
        self.setLayout(self.layout)

        # fitting module widgets
        module_sel_widget = QtWidgets.QWidget()
        module_sel_grid = QtWidgets.QGridLayout()
        # model function selection widget
        self.module_combo = self.addModuleComboBox()
        self.module_combo.currentTextChanged.connect(self.moduleUpdate)
        self.module_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                        QtWidgets.QSizePolicy.Expanding)
        module_sel_grid.addWidget(self.module_combo, 0, 0)
        # refresh module button
        # refresh_button = QtWidgets.QPushButton(REFRESH_MODULE_ICON, "")
        refresh_button = QtWidgets.QPushButton("↻")
        refresh_button.clicked.connect(self.moduleRefreshClicked)
        refresh_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                     QtWidgets.QSizePolicy.Fixed)
        module_sel_grid.addWidget(refresh_button, 0, 1)
        # add module button
        # open_button = QtWidgets.QPushButton(OPEN_MODULE_ICON,"")
        open_button = QtWidgets.QPushButton("+")
        open_button.clicked.connect(self.add_user_module)
        open_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                  QtWidgets.QSizePolicy.Fixed)
        module_sel_grid.addWidget(open_button, 0, 2)
        module_sel_widget.setLayout(module_sel_grid)
        self.layout.addWidget(module_sel_widget)


        # model list widget
        self.model_list = QtWidgets.QListWidget()
        self.layout.addWidget(self.model_list)
        self.moduleUpdate(self.module_combo.currentText())
        self.model_list.currentItemChanged.connect(self.modelChanged)

        # function description window
        self.model_doc_box = QtWidgets.QLineEdit("")
        self.model_doc_box.setReadOnly(True)
        self.layout.addWidget(self.model_doc_box)


        # parameter table
        self.param_table = QtWidgets.QTableWidget(0, 4)
        self.param_table.setHorizontalHeaderLabels([
            'fix', 'initial guess', 'lower bound', 'upper bound'])
        self.param_table.horizontalHeader(). \
            setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.layout.addWidget(self.param_table)

        # fitting update options
        self.addUpdateOptions()

        # getter and setter
        self.optGetters['fitting_options'] = self.fittingOptionGetter
        self.optSetters['fitting_options'] = self.fittingOptionSetter


    def addModuleComboBox(self):
        """ Set up the model function drop down manual widget.
        """
        combo = QtWidgets.QComboBox()
        combo.setEditable(False)
        for module_name in self.fitting_modules:
            combo.addItem(module_name)
        return combo

    @Slot(str)
    def moduleUpdate(self, current_module_name):
        if DEBUG:
            print ("moduleUpdate called", current_module_name)
        self.model_list.clear()
        current_module = self.fitting_modules[current_module_name]
        new_models = get_models_in_module(current_module)
        for model_name in new_models:
            self.model_list.addItem(model_name)

        # debug-------------------------------------------
        """
        fitters.generic_functions.Cosine.pp(1)
        try:
            test = fitters.generic_functions.Exponential2
            print("Exponential2 is here!!!!!")
        except :
            print("No Exponential2 :( ")
        """
        #-------------------------------------------------

    @Slot()
    def moduleRefreshClicked(self):
        self.moduleUpdate(self.module_combo.currentText())

    def add_user_module(self):
        mod_file = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open file',fitters.__path__[0], "Python files (""*.py)")[0]
        if (mod_file is None) or mod_file[-3:] !=".py":
            return
        mod_name = mod_file.split('/')[-1][:-3]
        mod_dir = '\\'.join(mod_file.split('/')[:-1])
        # load the selected module
        sys.path.append(mod_dir)
        user_module = import_module(mod_name, mod_dir)
        # debug-------------------------------------------
        """
        spec = importlib.util.spec_from_file_location(mod_name, mod_path)
        user_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(user_module)
        """
        #-------------------------------------------------
        # check if there is already a module with the same name
        if mod_name in self.fitting_modules:
            for existing_module in self.fitting_modules.values():
                if user_module.__file__ == existing_module.__file__:
                    # a module that already exists is loaded
                    print("a module that already exists is loaded")
                    self.module_combo.setCurrentText(mod_name)
                    self.moduleUpdate(mod_name)
                    return
            # a different module whose name is the same as one of the
            # existing modules is loaded
            print("a different module whose name is the same as one of "
                  "the existing modules is loaded")
            mod_name += f"({mod_dir})"

        self.fitting_modules[mod_name] = user_module
        self.module_combo.addItem(mod_name)
        self.module_combo.setCurrentText(mod_name)


    @Slot(QtWidgets.QListWidgetItem, QtWidgets.QListWidgetItem)
    def modelChanged(self,
                     current: QtWidgets.QListWidgetItem,
                     previous: QtWidgets.QListWidgetItem):
        """ Process a change in fit model selection.
        Will update the parameter table based on the new selection.
        """
        if current is None:
            print ("No model selected")
            self.model_doc_box.setText("")
            self.param_table.setRowCount(0)
            return
        current_module = self.fitting_modules[self.module_combo.currentText()]
        model_cls = getattr(current_module, current.text())
        self.updateParamTable(model_cls)
        self.model_doc_box.setText(model_cls.model.__doc__)

    def updateParamTable(self, model_cls: Type[Fit]):
        """ Update the parameter table based on the current model selection.
        :param model_cls: the current selected fitting model class
        """
        # flush param table
        self.param_table.setRowCount(0)
        # rebuild param table based on the selected model function
        func = model_cls.model
        # assume the first variable is the independent variable
        params = list(inspect.signature(func).parameters)[1:]
        self.param_table.setRowCount(len(params))
        self.param_table.setVerticalHeaderLabels(params)
        # generate fix, initial guess, lower/upper bound option GUIs for each
        # parameter
        self.param_signals = []
        for idx, name in enumerate(params):
            fixParamCheck = self._paramFixCheck()
            fixParamCheck.setStyleSheet("margin-left:15%; margin-right:5%;")
            initialGuessBox = OptionSpinbox(1.0, self)
            lowerBoundBox = NumberInput(None, self)
            upperBoundBox = NumberInput(None, self)
            lowerBoundBox.newTextEntered.connect(initialGuessBox.setMinimum)
            upperBoundBox.newTextEntered.connect(initialGuessBox.setMaximum)

            # gather the param change signals for enabling live update
            self.param_signals.extend((fixParamCheck.stateChanged,
                                       initialGuessBox.valueChanged,
                                       lowerBoundBox.newTextEntered,
                                       upperBoundBox.newTextEntered))
            # put param options into table
            self.param_table.setCellWidget(idx, 0, fixParamCheck)
            self.param_table.setCellWidget(idx, 1, initialGuessBox)
            self.param_table.setCellWidget(idx, 2, lowerBoundBox)
            self.param_table.setCellWidget(idx, 3, upperBoundBox)

        self.changeParamLiveUpdate(self.live_update)

    def _paramFixCheck(self, default_value: bool = False):
        """generate a push checkbox for the parameter fix option.
        :param default_value : param is fixed by default or not
        :returns: a checkbox widget
        """
        widget = QtWidgets.QCheckBox('')
        widget.setChecked(default_value)
        widget.setToolTip("when fixed, the parameter will be fixed to the "
                          "initial guess value during fitting")
        return widget

    def addUpdateOptions(self):
        ''' Add check box & buttons that control the fitting update policy.
        '''
        widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout()
        # when checked, fitting will update after each change of fitting model
        # or parameter option
        liveUpdateCheck = QtWidgets.QCheckBox('Live Update')
        grid.addWidget(liveUpdateCheck, 0, 0)
        # update fitting on-demand
        updateFitButton = QtWidgets.QPushButton("Fit")
        grid.addWidget(updateFitButton, 0, 1)
        # reload the fitting options that come from the data
        reloadInputOptButton = QtWidgets.QPushButton("Reload Input Option")
        grid.addWidget(reloadInputOptButton, 0, 2)

        @Slot(QtCore.Qt.CheckState)
        def setLiveUpdate(live: QtCore.Qt.CheckState):
            ''' connect/disconnects the changing signal of each fitting
            option to signalAllOptions slot
            '''
            if live == QtCore.Qt.Checked:
                self.model_list.currentItemChanged.connect(self._signalAllOptions)
                self.changeParamLiveUpdate(True)
                self.live_update = True
            else:
                try:
                    self.model_list.currentItemChanged.disconnect(
                        self._signalAllOptions)
                except TypeError:
                    pass
                self.changeParamLiveUpdate(False)
                self.live_update = False

        @Slot()
        def reloadInputOption():
            if DEBUG:
                print("reload input option")
            self.fittingOptionSetter(self.input_options)

        liveUpdateCheck.stateChanged.connect(setLiveUpdate)
        updateFitButton.pressed.connect(self.signalAllOptions)
        reloadInputOptButton.pressed.connect(reloadInputOption)
        reloadInputOptButton.setToolTip('reload the fitting options stored '
                                        'in the input data')

        widget.setLayout(grid)
        self.layout.addWidget(widget)

    def changeParamLiveUpdate(self, enable: bool):
        ''' connect/disconnects the changing signal of each fitting param
        option to signalAllOptions slot
        :param enable: connect/disconnect when enable is True/False.
        '''
        if enable:
            for psig in self.param_signals:
                psig.connect(self._signalAllOptions)
        else:
            for psig in self.param_signals:
                try:
                    psig.disconnect(self._signalAllOptions)
                except TypeError:
                    pass


    def fittingOptionGetter(self) -> Optional[FittingOptions]:
        """ get all the fitting options and put them into a dictionary
        """
        if DEBUG:
            print('getter in gui called')
        # get the current model selected
        current_module = self.fitting_modules[self.module_combo.currentText()]
        model_selected = self.model_list.currentItem()
        if model_selected is None:
            return
        model = getattr(current_module, model_selected.text())
        # get the parameters for current model
        parameters = lmParameters()
        for i in range(self.param_table.rowCount()):
            param_name = self.param_table.verticalHeaderItem(i).text()
            param = lmParameter(param_name)
            get_cell = self.param_table.cellWidget
            param.vary = not get_cell(i, 0).isChecked()
            param.value = get_cell(i, 1).value()
            param.min = get_cell(i, 2).value()
            param.max = get_cell(i, 3).value()
            parameters[param_name] = param

        fitting_options = FittingOptions(model, parameters)
        if DEBUG:
            print('getter in gui got', fitting_options)
        return fitting_options

    def fittingOptionSetter(self, fitting_options: FittingOptions):
        """ Set all the fitting options
        """
        if DEBUG:
            print('setter in gui called')
        if fitting_options is None:
            return

        # set the model in gui
        model = fitting_options.model
        if DEBUG:
            print(f"setter trying to set model to {model}")
        # try to find the module that contains the model first
        module_exist = False
        for mdu_name, mdu in self.fitting_modules.items():
            if mdu.__file__ == inspect.getsourcefile(model):
                self.module_combo.setCurrentText(mdu_name)
                if DEBUG:
                    print(f"setter set module to {mdu_name}")
                module_exist = True
                break
        # set the model in model list
        if module_exist:
            model_cls_name = model.__qualname__
            find_mdls = self.model_list.findItems(model_cls_name,
                                                  QtCore.Qt.MatchExactly)
            if len(find_mdls) == 1:
                self.model_list.setCurrentItem(find_mdls[0])
            else:
                if DEBUG:
                    print("unexpected Error when trying to find the module")
                    print(model_cls_name)
                else:
                    raise NameError("unexpected Error when trying to find the module")
        else:
            #TODO: fix this, add the new model to gui
            raise NotImplementedError("auto add new model to gui")
        if DEBUG:
            print('in setter, model set to ', model)
            print('now fitting_options is ', fitting_options)
            print('all_param_options is ', fitting_options.parameters)

        # set the parameter table in gui
        for i in range(self.param_table.rowCount()):
            param_name = self.param_table.verticalHeaderItem(i).text()
            param_options = fitting_options.parameters[param_name]
            get_cell = self.param_table.cellWidget
            get_cell(i, 0).setChecked(not param_options.vary)
            get_cell(i, 1).setValue(param_options.value)
            get_cell(i, 2).setValue(param_options.min)
            get_cell(i, 3).setValue(param_options.max)


    def _signalAllOptions(self, *args):
        # to make the signalAllOptions accept signals w/ multi args
        if DEBUG:
            print("signal option change")
        if self.model_list.currentItem() is not None:
            self.signalAllOptions()

    @updateGuiFromNode
    def setDefaultFit(self, fitting_options: FittingOptions):
        ''' set the gui to the fitting options in the input data
        '''
        if DEBUG:
            print(f'updateGuiFromNode function got {fitting_options}')
        self.fittingOptionSetter(fitting_options)
        if self.input_options is None:
            self.input_options = fitting_options


class OptionSpinbox(QtWidgets.QDoubleSpinBox):
    """A spinBox widget for parameter options
    :param default_value : default value of the option
    """

    # TODO: Support easier input for large numbers
    def __init__(self, default_value=1.0, parent=None):
        super().__init__(parent)
        self.setRange(-1 * MAX_FLOAT, MAX_FLOAT)
        self.setValue(default_value)

    def setMaximum(self, maximum):
        try:
            value = eval(maximum)
        except:
            value = MAX_FLOAT
        if isinstance(value, numbers.Number):
            super().setMaximum(value)
        else:
            super().setMaximum(MAX_FLOAT)

    def setMinimum(self, minimum):
        try:
            value = eval(minimum)
        except:
            value = -1 * MAX_FLOAT
        if isinstance(value, numbers.Number):
            super().setMinimum(value)
        else:
            super().setMinimum(-1 * MAX_FLOAT)


class NumberInput(QtWidgets.QLineEdit):
    """A text edit widget that checks whether its input can be read as a
    number.
    This is copied form the parameter GUI that Wolfgang wrote for the
    parameter manager gui.
    """
    newTextEntered = Signal(str)

    def __init__(self, default_value, parent=None):
        super().__init__(parent)
        self.setValue(default_value)
        self.editingFinished.connect(self.emitNewText)

    def value(self):
        try:
            value = eval(self.text())
        except:
            return None
        if isinstance(value, numbers.Number):
            return value
        else:
            return None

    def setValue(self, value):
        self.setText(str(value))

    def emitNewText(self):
        self.newTextEntered.emit(self.text())


# ================= Node ==============================
class FittingNode(Node):
    uiClass = FittingGui
    nodeName = "Fitter"
    default_fitting_options = Signal(object)

    def __init__(self, name):
        super().__init__(name)
        self._fitting_options = None

    def process(self, dataIn: DataDictBase = None):
        return self.fitting_process(dataIn)

    @property
    def fitting_options(self):
        return self._fitting_options

    @fitting_options.setter
    @updateOption('fitting_options')
    def fitting_options(self, opt):
        if isinstance(opt, FittingOptions) or opt is None:
            self._fitting_options = opt
        else:
            raise TypeError('Wrong fitting options')

    def fitting_process(self, dataIn: DataDictBase = None):
        if dataIn is None:
            return None

        if len(dataIn.axes()) > 1 or len(dataIn.dependents()) > 1:
            return dict(dataOut=dataIn)

        dataIn_opt = dataIn.get('__fitting_options__')
        dataOut = dataIn.copy()

        if self.fitting_options is None:
            if dataIn_opt is not None:
                if DEBUG:
                    print("Emit initial option from "
                          "process!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", dataIn_opt)
                self.default_fitting_options.emit(dataIn_opt)
                self._fitting_options = dataIn_opt
            else:
                return dict(dataOut=dataOut)

        # fitting process
        if DEBUG:
            print("in process!!!!!!!!!!!!!\n", self.fitting_options)

        axname = dataIn.axes()[0]
        x = dataIn.data_vals(axname)
        y = dataIn.data_vals(dataIn.dependents()[0])

        fit = self.fitting_options.model(x, y)
        fit_result = fit.run(params = self.fitting_options.parameters)
        lm_result = fit_result.lmfit_result

        if lm_result.success:
            dataOut['fit'] = dict(values=lm_result.best_fit, axes=[axname, ])
            dataOut.add_meta('info', lm_result.fit_report())

        return dict(dataOut=dataOut)


    def setupUi(self):
        super().setupUi()
        self.default_fitting_options.connect(self.ui.setDefaultFit)

        # debug
        # axname = dataIn.axes()[0]
        # x = dataIn.data_vals(axname)
        # model_str = self.fitting_options.model.split('.')
        # func = MODEL_FUNCS[model_str[0]][model_str[1]]
        # fit_params = self.fitting_options.parameters
        # func_args = {arg: fit_params[arg].initialGuess for arg in fit_params}
        #
        # dataOut = dataIn.copy()
        # dataOut['fit'] = dict(values=func(x,**func_args), axes=[axname, ])
        # return dict(dataOut=dataOut)