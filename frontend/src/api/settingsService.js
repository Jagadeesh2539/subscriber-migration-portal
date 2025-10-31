import axios from 'axios';

export const settingsService = {
  getProvisioningMode: () => axios.get('/settings/provisioning-mode'),
  setProvisioningMode: (mode) => axios.put('/settings/provisioning-mode', { mode }),
};
